"""서빙 엔진 비교 측정.

    # 엔진을 하나씩 자동으로 띄우고 재고 내린다 (8GB GPU 권장 방식)
    python scripts/bench_serving.py configs/serving_laptop.yaml --manage

    # 이미 떠 있는 엔진 하나만
    python scripts/bench_serving.py configs/serving_laptop.yaml --only vLLM

    # 빨리 동작만 확인
    python scripts/bench_serving.py configs/serving_laptop.yaml --only vLLM --quick

결과: results/<이름>.json, results/<이름>.md  (확정본은 사람이 골라 reports/ 로 옮긴다)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from onprem_agent.serving.bench import run_level, summarize  # noqa: E402
from onprem_agent.serving.report import to_markdown  # noqa: E402
from onprem_agent.serving.toolcheck import load_cases, run_toolcheck  # noqa: E402
from onprem_agent.serving.workloads import build_workloads  # noqa: E402

COMPOSE = ["docker", "compose", "-f", str(ROOT / "serving/compose.yml")]


def compose(profiles, action):
    profiles = profiles if isinstance(profiles, list) else [profiles]
    args = [a for p in profiles for a in ("--profile", p)]
    cmd = COMPOSE + args + (["up", "-d"] if action == "up" else ["down"])
    print("  $", " ".join(cmd[3:]))
    subprocess.run(cmd, check=True)


def wait_ready(base_url, headers, timeout_s):
    """/models 가 200 을 줄 때까지 기다린다. 첫 실행은 모델 내려받기 때문에 수 분 걸릴 수 있다."""
    import httpx
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            if httpx.get(f"{base_url}/models", headers=headers, timeout=5).status_code == 200:
                print(f"  준비 완료 ({time.time() - t0:.0f}s)")
                return
        except Exception:
            pass
        time.sleep(5)
    raise TimeoutError(f"{base_url} 가 {timeout_s}s 안에 준비되지 않음 (docker compose -f serving/compose.yml logs 확인)")


def engine_info(url):
    if not url:
        return None
    import httpx
    try:
        j = httpx.get(url, timeout=5).json()
        keep = ("version", "build_info", "model_path", "default_generation_settings", "chat_template_kwargs")
        return {k: j[k] for k in keep if k in j} or {"raw": str(j)[:300]}
    except Exception as e:
        return {"error": str(e)[:100]}


async def bench_engine(eng, cfg, jobs_by_level, quick):
    headers = eng.get("headers", {})
    extra = {**cfg.get("extra", {}), **eng.get("extra", {})}
    out = {"label": eng["label"], "base_url": eng["base_url"], "info": engine_info(eng.get("info_url")), "workloads": {}}
    # 예열: 첫 요청은 CUDA 그래프·커널 준비 때문에 느리다. 측정에서 뺀다.
    warm = jobs_by_level[cfg["levels"][0]]["rag"][:2]
    await run_level(eng["base_url"], eng["model"], warm, 2, 16, extra, headers)
    for w in eng.get("workloads", cfg["workloads"]):
        out["workloads"][w] = []
        for lv in cfg["levels"]:
            jobs = jobs_by_level[lv][w]
            results, dur = await run_level(eng["base_url"], eng["model"], jobs, lv, cfg["max_tokens"], extra, headers)
            s = summarize(results, dur, cfg["slo"])
            out["workloads"][w].append({"concurrency": lv, "summary": s})
            ch = s["cache_hit_ratio"]
            print(f"  [{eng['label']}] {w:<9} 동시 {lv:>2}  {s['req_per_s']:5.2f} req/s  {s['out_tok_per_s']:6.0f} tok/s  "
                  f"TTFT p50 {s['ttft_ms']['p50'] or 0:6.0f}ms  TPOT p50 {s['tpot_ms']['p50'] or 0:5.1f}ms  "
                  f"굿풋 {s['goodput_req_per_s']:.2f}  캐시 {'—' if ch is None else f'{ch:.0%}'}  오류 {s['errors']}")
            if s["errors"]:
                print("     오류 예:", s["error_samples"][:1])
    if eng.get("toolcheck", True) and cfg.get("toolcheck"):
        cases = load_cases(ROOT / cfg["toolcheck"])
        if quick:
            cases = cases[:5]
        tc_extra = {"chat_template_kwargs": cfg.get("extra", {}).get("chat_template_kwargs", {})}
        t = await run_toolcheck(eng["base_url"], eng["model"], cases, tc_extra, headers)
        out["toolcheck"] = t
        print(f"  [{eng['label']}] 도구 호출: 도구 선택 {t['tool_accuracy']:.2f}, 인자까지 {t['args_accuracy']:.2f}, "
              f"형식 오류 {t['parse_errors']}, 요청 오류 {t['request_errors']}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--only", nargs="*", help="이 문자열이 이름에 들어간 엔진만")
    ap.add_argument("--manage", action="store_true", help="엔진마다 docker compose 로 띄우고 내린다")
    ap.add_argument("--quick", action="store_true", help="동작 확인용: 동시 1·4, 요청 8개, 도구 검사 5문항")
    ap.add_argument("--ready-timeout", type=int, default=1200)
    a = ap.parse_args()

    cfg = yaml.safe_load(Path(a.config).read_text(encoding="utf-8"))
    if a.quick:
        cfg.update(levels=[1, 4], requests_per_level=8, name=cfg["name"] + "_quick")
    turns = 3
    jobs_by_level = {}
    for lv in cfg["levels"]:
        # 동시 사용자 단계마다 다른 요청 묶음(시드)을 쓴다. 앞 단계가 남긴 캐시를 다음 단계가 공짜로 쓰지 않게.
        n = cfg["requests_per_level"]
        wl = build_workloads(ROOT, n, seed=1000 + lv, turns=turns)
        # 대화 수가 동시 사용자 수보다 적으면 일부 사용자가 놀게 된다 → 최소한 동시 사용자 수만큼 대화를 만든다
        wl["multiturn"] = wl["multiturn"][: max(lv, n // turns)]
        jobs_by_level[lv] = wl

    res = {"config_name": cfg["name"], "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "model_note": cfg.get("model_note", ""), "max_tokens": cfg["max_tokens"],
           "requests_per_level": cfg["requests_per_level"], "levels": cfg["levels"], "slo": cfg["slo"], "engines": []}
    for eng in cfg["engines"]:
        if a.only and not any(o in eng["label"] for o in a.only):
            continue
        print(f"\n== {eng['label']}")
        try:
            if a.manage:
                compose(eng["profile"], "up")
            for url in eng.get("wait_for", []):      # 게이트웨이 뒤의 엔진이 먼저 준비돼야 한다
                wait_ready(url, {}, a.ready_timeout if a.manage else 10)
            wait_ready(eng["base_url"], eng.get("headers", {}), a.ready_timeout if a.manage else 10)
            res["engines"].append(asyncio.run(bench_engine(eng, cfg, jobs_by_level, a.quick)))
        except Exception as e:
            print(f"  건너뜀: {type(e).__name__}: {str(e)[:200]}")
            res["engines"].append({"label": eng["label"], "error": f"{type(e).__name__}: {str(e)[:300]}"})
        finally:
            if a.manage:
                compose(eng["profile"], "down")

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / f"{cfg['name']}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"{cfg['name']}.md").write_text(to_markdown(res), encoding="utf-8")
    print(f"\n저장: results/{cfg['name']}.json, results/{cfg['name']}.md")


if __name__ == "__main__":
    main()
