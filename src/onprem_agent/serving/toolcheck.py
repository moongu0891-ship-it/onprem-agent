"""업무 기능(도구) 호출 검사: 엔진이 질문에 맞는 업무 기능(도구)을 고르고 인자를 바르게 채우는지.

에이전트에서는 속도보다 이게 먼저다. 같은 모델이라도 엔진마다 '모델 출력 → tool_calls JSON'으로 바꾸는
파서가 달라서(vLLM hermes, SGLang qwen25, llama.cpp --jinja) 결과가 달라질 수 있다.

채점
- 업무 기능(도구) 선택: 기대한 업무 기능(도구) 이름과 같은가 (업무 기능(도구)이 필요 없는 질문은 '안 부름'이 정답)
- 인자: 기대한 인자 값이 모두 맞는가 (문자열은 대소문자·공백 무시, 숫자는 값 비교)
- 형식 오류: tool_calls 의 arguments 가 JSON 으로 안 읽히는 경우
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .tools import TOOLS


def load_cases(path: Path) -> list[dict]:
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def _norm(v):
    if isinstance(v, str):
        s = v.strip().lower().replace(" ", "")
        return int(s) if s.isdigit() else s
    return v


def score_case(case: dict, message: dict) -> dict:
    calls = message.get("tool_calls") or []
    want = case.get("tool")
    row = {"id": case["id"], "want": want, "got": None, "name_ok": False, "args_ok": False, "parse_error": False}
    if not calls:
        row["name_ok"] = row["args_ok"] = want is None
        return row
    fn = calls[0].get("function") or {}
    row["got"] = fn.get("name")
    try:
        args = fn.get("arguments") or "{}"
        args = json.loads(args) if isinstance(args, str) else args
    except json.JSONDecodeError:
        row["parse_error"] = True
        return row
    row["args"] = args
    row["name_ok"] = row["got"] == want
    expect = case.get("args", {})
    row["args_ok"] = row["name_ok"] and all(
        (k in args and str(args[k]).strip() != "") if v == "*" else _norm(args.get(k)) == _norm(v)
        for k, v in expect.items())
    return row


async def run_toolcheck(base_url: str, model: str, cases: list[dict], extra: dict | None = None,
                        headers: dict | None = None, timeout: float = 120.0) -> dict:
    import httpx

    rows, lat = [], []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for c in cases:
            body = {"model": model, "temperature": 0.0, "max_tokens": 256, "tools": TOOLS, "tool_choice": "auto",
                    "messages": [{"role": "system", "content": "필요하면 도구를 호출하세요. 도구가 필요 없으면 바로 답하세요."},
                                 {"role": "user", "content": c["question"]}], **(extra or {})}
            t = time.perf_counter()
            try:
                r = await client.post(f"{base_url.rstrip('/')}/chat/completions", json=body, headers=headers or {})
                r.raise_for_status()
                msg = r.json()["choices"][0]["message"]
            except Exception as e:
                rows.append({"id": c["id"], "want": c.get("tool"), "got": None, "name_ok": False, "args_ok": False,
                             "parse_error": False, "error": f"{type(e).__name__}: {e}"[:200]})
                continue
            lat.append((time.perf_counter() - t) * 1000)
            rows.append(score_case(c, msg))
    n = len(rows)
    return {
        "n": n,
        "tool_accuracy": sum(r["name_ok"] for r in rows) / n if n else 0.0,
        "args_accuracy": sum(r["args_ok"] for r in rows) / n if n else 0.0,
        "parse_errors": sum(r["parse_error"] for r in rows),
        "request_errors": sum(1 for r in rows if r.get("error")),
        "latency_ms_p50": sorted(lat)[len(lat) // 2] if lat else None,
        "misses": [r for r in rows if not r["args_ok"]],
    }
