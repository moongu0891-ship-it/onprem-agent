"""장애 대체 시험의 기록·요약 (Docker 를 다루는 부분은 scripts/failover_test.py).

시험 순서
1. 정상      : 게이트웨이(agent-llm)로 요청 → 1순위(SGLang)가 받아야 한다.
2. 장애      : 요청을 계속 보내는 도중에 1순위 컨테이너를 멈춘다 → 대체(CPU llama.cpp)로 넘어가야 한다.
              멈추는 순간 처리 중이던 요청이 실패하는지, 몇 초 만에 대체로 넘어가는지 본다.
3. 복구      : 1순위를 다시 띄운다 → 다시 1순위로 돌아와야 한다.

어느 엔진이 답했는지는 두 가지로 확인한다.
- 게이트웨이 응답 헤더 x-litellm-model-group (agent-llm = 1순위, agent-llm-backup = 대체), 요청마다
- llama.cpp 의 처리 토큰 누계(/metrics) 증가 (단계마다, 게이트웨이와 독립된 증거)
"""

from __future__ import annotations

from collections import Counter

from ..eval.metrics import percentile


def classify_backend(headers: dict) -> str:
    """LiteLLM 응답 헤더로 답한 엔진을 판별한다.
    x-litellm-model-group(비스트리밍 응답에 실림): agent-llm = 1순위, agent-llm-backup = 대체. api_base 헤더가 있으면 그걸 먼저 본다."""
    h = {k.lower(): v for k, v in headers.items()}
    base = h.get("x-litellm-model-api-base", "")
    group = h.get("x-litellm-model-group", "")
    if not base and group:
        if group == "agent-llm-backup":
            return "llama.cpp(CPU)"
        if group == "agent-llm":
            return "SGLang"
    if "sglang" in base:
        return "SGLang"
    if "llamacpp" in base:
        return "llama.cpp(CPU)"
    if "vllm" in base:
        return "vLLM"
    return "알 수 없음"


def parse_metric(text: str, name: str) -> float | None:
    for line in text.splitlines():
        if line.startswith(name + " ") or line.startswith(name + "{"):
            try:
                return float(line.rsplit(" ", 1)[1])
            except ValueError:
                return None
    return None


def summarize_phase(records: list[dict], t_event: float | None = None) -> dict:
    ok = [r for r in records if r["ok"]]
    lat = [r["ms"] for r in ok]
    out = {
        "requests": len(records), "ok": len(ok), "failed": len(records) - len(ok),
        "backends": dict(Counter(r["backend"] for r in ok)),
        "latency_ms": {"p50": percentile(lat, 50) if lat else None, "p95": percentile(lat, 95) if lat else None},
        "errors": [{"t": round(r["t"] - (t_event or 0), 2), "error": r["error"]} for r in records if not r["ok"]][:5],
    }
    if t_event is not None:
        # 사건(멈춤·재시작) 이후 처음으로 '다른 엔진'이 답한 시각
        after = [r for r in records if r["t"] >= t_event and r["ok"]]
        out["first_ok_after_event_s"] = round(after[0]["t"] - t_event, 2) if after else None
        out["failed_after_event"] = sum(1 for r in records if r["t"] >= t_event and not r["ok"])
    return out


def to_markdown(res: dict) -> str:
    lines = ["# 장애 대체 시험", "",
             f"- 실행: {res['started_at']} · 1순위 {res['primary']} · 대체 {res['backup']} · 게이트웨이 LiteLLM (`agent-llm`)",
             f"- 요청: 짧은 질문, 출력 {res['max_tokens']}토큰, 동시 {res['workers']}개씩 계속 보냄", "",
             "| 단계 | 요청 | 성공 | 실패 | 답한 엔진 | 지연 p50 (ms) | 지연 p95 (ms) | llama.cpp 처리 토큰 증가 |",
             "|---|---|---|---|---|---|---|---|"]
    for ph in res["phases"]:
        s = ph["summary"]
        be = ", ".join(f"{k} {v}" for k, v in s["backends"].items()) or "—"
        p50 = "—" if s["latency_ms"]["p50"] is None else f"{s['latency_ms']['p50']:.0f}"
        p95 = "—" if s["latency_ms"]["p95"] is None else f"{s['latency_ms']['p95']:.0f}"
        d = ph.get("backup_tokens_delta")
        lines.append(f"| {ph['name']} | {s['requests']} | {s['ok']} | {s['failed']} | {be} | {p50} | {p95} "
                     f"| {'—' if d is None else f'{d:.0f}'} |")
    lines.append("")
    for ph in res["phases"]:
        s = ph["summary"]
        if "first_ok_after_event_s" in s:
            lines.append(f"- {ph['name']}: {ph.get('event', '사건')} 후 첫 성공까지 {s['first_ok_after_event_s']} 초, "
                         f"그 뒤 실패 {s['failed_after_event']}건")
        for e in s["errors"]:
            lines.append(f"  - 실패 예 (사건 기준 {e['t']}s): {e['error'][:200]}")
    if res.get("headers_sample"):
        lines += ["", "게이트웨이 응답 헤더 예: `" + ", ".join(f"{k}={v}" for k, v in res["headers_sample"].items()) + "`"]
    return "\n".join(lines)
