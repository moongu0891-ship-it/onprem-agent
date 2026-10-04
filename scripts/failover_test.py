"""장애 대체 시험: 1순위 엔진(SGLang)을 끄면 게이트웨이가 대체 엔진(CPU llama.cpp)으로 넘기는가.

    python scripts/failover_test.py

결과: results/failover.json, results/failover.md
SGLang(GPU) · llama.cpp(CPU) · LiteLLM 을 함께 띄우고, 끝나면 모두 내린다.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from onprem_agent.serving.failover import classify_backend, parse_metric, summarize_phase, to_markdown  # noqa: E402

COMPOSE = ["docker", "compose", "-f", str(ROOT / "serving/compose.yml")]
PROFILES = ["sglang-g16", "llamacpp-cpu", "litellm"]
PRIMARY_SVC = "sglang-g16"
GW = "http://localhost:4000/v1"
HEADERS = {"Authorization": "Bearer sk-local-dev"}
PRIMARY = "http://localhost:30000/v1"
BACKUP = "http://localhost:18082/v1"
BACKUP_METRICS = "http://localhost:18082/metrics"
MAX_TOKENS = 16
WORKERS = 2


def dc(*args, check=True):
    pa = [a for p in PROFILES for a in ("--profile", p)]
    print("  $ docker compose", " ".join(args))
    return subprocess.run(COMPOSE + pa + list(args), check=check, capture_output=not check, text=True)


def wait(url, headers=None, timeout=900):
    import httpx
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if httpx.get(f"{url}/models", headers=headers or {}, timeout=5).status_code == 200:
                print(f"  준비 완료: {url} ({time.time() - t0:.0f}s)")
                return
        except Exception:
            pass
        time.sleep(5)
    raise TimeoutError(f"{url} 준비 안 됨")


def backup_tokens():
    import httpx
    try:
        return parse_metric(httpx.get(BACKUP_METRICS, timeout=5).text, "llamacpp:tokens_predicted_total")
    except Exception:
        return None


def ask(client, i, t0, sample):
    body = {"model": "agent-llm", "max_tokens": MAX_TOKENS, "temperature": 0.0,
            "messages": [{"role": "user", "content": f"[{i}] KX-200 설비의 LVL-06 경보는 무엇인가요? 한 문장으로."}],
            "chat_template_kwargs": {"enable_thinking": False}}
    t = time.perf_counter()
    try:
        r = client.post(f"{GW}/chat/completions", json=body, headers=HEADERS)
        ms = (time.perf_counter() - t) * 1000
        hdr = {k: v for k, v in r.headers.items() if k.lower().startswith("x-litellm")}
        if r.status_code != 200:
            return {"t": t - t0, "ok": False, "ms": ms, "backend": None, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        if not sample:
            sample.update(hdr)
        return {"t": t - t0, "ok": True, "ms": ms, "backend": classify_backend(hdr), "error": None}
    except Exception as e:
        return {"t": t - t0, "ok": False, "ms": (time.perf_counter() - t) * 1000, "backend": None,
                "error": f"{type(e).__name__}: {e}"[:200]}


class Load:
    """백그라운드에서 요청을 계속 보낸다 (워커 WORKERS 개, 요청 사이 0.5초)."""

    def __init__(self, t0, sample):
        import httpx
        self.client = httpx.Client(timeout=120)
        self.t0, self.sample, self.records, self.stop, self.i = t0, sample, [], threading.Event(), 0
        self.lock = threading.Lock()
        self.threads = [threading.Thread(target=self.run, daemon=True) for _ in range(WORKERS)]

    def run(self):
        while not self.stop.is_set():
            with self.lock:
                self.i += 1
                i = self.i
            rec = ask(self.client, i, self.t0, self.sample)
            with self.lock:
                self.records.append(rec)
            time.sleep(0.5)

    def __enter__(self):
        for th in self.threads:
            th.start()
        return self

    def take(self):
        with self.lock:
            out, self.records = self.records, []
        return out

    def __exit__(self, *a):
        self.stop.set()
        for th in self.threads:
            th.join(timeout=130)
        self.client.close()


def main():
    t0 = time.perf_counter()
    sample: dict = {}
    res = {"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "primary": "SGLang (GPU, 그래프≤16)",
           "backup": "llama.cpp (CPU, Q8_0)", "max_tokens": MAX_TOKENS, "workers": WORKERS, "phases": []}
    try:
        dc("up", "-d")
        wait(PRIMARY)
        wait(BACKUP)
        wait(GW, HEADERS)
        with Load(t0, sample) as load:
            # 1) 정상
            b0 = backup_tokens()
            time.sleep(15)
            recs = load.take()
            res["phases"].append({"name": "1 정상", "summary": summarize_phase(recs),
                                  "backup_tokens_delta": (backup_tokens() or 0) - (b0 or 0) if b0 is not None else None})
            print("  1 정상:", res["phases"][-1]["summary"]["backends"])

            # 2) 장애: 1순위를 멈춘다
            b0 = backup_tokens()
            t_stop = time.perf_counter() - t0
            dc("stop", PRIMARY_SVC)
            time.sleep(30)
            recs = load.take()
            res["phases"].append({"name": "2 장애 (1순위 멈춤)", "event": "1순위 멈춤",
                                  "summary": summarize_phase(recs, t_stop),
                                  "backup_tokens_delta": (backup_tokens() or 0) - (b0 or 0) if b0 is not None else None})
            print("  2 장애:", res["phases"][-1]["summary"]["backends"], "실패", res["phases"][-1]["summary"]["failed"])

            # 3) 복구: 1순위를 다시 띄운다 (뜨는 동안에도 요청은 계속 → 대체가 받아야 한다)
            b0 = backup_tokens()
            t_start = time.perf_counter() - t0
            dc("start", PRIMARY_SVC)
            wait(PRIMARY)
            t_ready = time.perf_counter() - t0
            time.sleep(20)
            recs = load.take()
            during = [r for r in recs if r["t"] < t_ready]
            after = [r for r in recs if r["t"] >= t_ready]
            res["phases"].append({"name": "3a 1순위 재시작 중", "summary": summarize_phase(during),
                                  "restart_s": round(t_ready - t_start, 1),
                                  "backup_tokens_delta": (backup_tokens() or 0) - (b0 or 0) if b0 is not None else None})
            res["phases"].append({"name": "3b 1순위 복구 후", "event": "1순위 준비 완료",
                                  "summary": summarize_phase(after, t_ready)})
            print("  3 복구:", res["phases"][-1]["summary"]["backends"], f"(재시작 {t_ready - t_start:.0f}s)")
    except Exception as e:
        res["error"] = f"{type(e).__name__}: {e}"[:300]
        print("  실패:", res["error"])
        logs = dc("logs", "--no-color", "--tail", "200", check=False)
        d = ROOT / "results/logs"
        d.mkdir(parents=True, exist_ok=True)
        (d / "failover.log").write_text(logs.stdout + logs.stderr, encoding="utf-8")
        print("  엔진 로그: results/logs/failover.log")
    finally:
        dc("down")
    res["headers_sample"] = sample
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / "failover.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "failover.md").write_text(to_markdown(res), encoding="utf-8")
    print("\n저장: results/failover.json, results/failover.md")


if __name__ == "__main__":
    main()
