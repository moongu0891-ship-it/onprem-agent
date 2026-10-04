"""동시 사용자 수를 바꿔 가며 엔진에 부하를 주고 지표를 낸다.

방식: 닫힌 루프(closed loop). 동시 사용자 N명이 각자 '요청 → 응답 끝 → 다음 요청'을 반복한다.
실제 에이전트처럼 앞 응답을 받아야 다음 요청을 만들 수 있는 대화(multiturn)도 같은 방식으로 돈다.

굿풋(goodput): 초당 처리한 요청 중 '목표(SLO)를 지킨 요청'만 센 것.
처리량만 보면 동시 사용자를 늘릴수록 좋아 보이지만, 그만큼 응답이 늦어진다.
"첫 토큰 1초 이내, 토큰당 50ms 이내" 같은 목표를 정해 두고 그걸 지킨 처리량을 봐야 실제로 몇 명을 받을 수 있는지 나온다.
"""

from __future__ import annotations

import asyncio
import time

from ..eval.metrics import percentile
from .client import RequestResult, stream_chat


async def run_level(base_url: str, model: str, jobs: list[dict], concurrency: int, max_tokens: int,
                    extra: dict | None = None, headers: dict | None = None, timeout: float = 300.0):
    import httpx

    queue: asyncio.Queue = asyncio.Queue()
    for j in jobs:
        queue.put_nowait(j)
    results: list[RequestResult] = []
    limits = httpx.Limits(max_connections=concurrency + 4, max_keepalive_connections=concurrency + 4)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        async def worker():
            while True:
                try:
                    job = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                messages = [{"role": "system", "content": job["system"]}]
                for turn in job["turns"]:
                    messages.append({"role": "user", "content": turn})
                    r = await stream_chat(client, base_url, model, messages, max_tokens, extra, headers)
                    results.append(r)
                    if not r.ok:
                        break       # 대화 중간에 실패하면 그 대화는 멈춘다
                    messages.append({"role": "assistant", "content": r.text})

        t0 = time.perf_counter()
        await asyncio.gather(*(worker() for _ in range(concurrency)))
        duration = time.perf_counter() - t0
    return results, duration


def summarize(results: list[RequestResult], duration: float, slo: dict) -> dict:
    ok = [r for r in results if r.ok]
    ttft = [r.ttft * 1000 for r in ok]
    tpot = [r.tpot * 1000 for r in ok if r.tpot is not None]
    itl = [x * 1000 for r in ok for x in r.itl]
    e2e = [r.e2e * 1000 for r in ok]
    good = [r for r in ok if r.ttft * 1000 <= slo["ttft_ms"] and (r.tpot is None or r.tpot * 1000 <= slo["tpot_ms"])]
    prompt = sum(r.prompt_tokens or 0 for r in ok)
    cached = [r.cached_tokens for r in ok if r.cached_tokens is not None]
    p = lambda xs, q: percentile(xs, q) if xs else None  # noqa: E731
    return {
        "requests": len(results), "errors": len(results) - len(ok),
        "error_samples": [r.error for r in results if not r.ok][:3],
        "duration_s": duration,
        "req_per_s": len(ok) / duration if duration else 0.0,
        "out_tok_per_s": sum(r.out_tokens for r in ok) / duration if duration else 0.0,
        "ttft_ms": {"p50": p(ttft, 50), "p95": p(ttft, 95)},
        "tpot_ms": {"p50": p(tpot, 50), "p95": p(tpot, 95)},
        "itl_ms": {"p95": p(itl, 95)},
        "e2e_ms": {"p50": p(e2e, 50), "p95": p(e2e, 95)},
        "slo_attainment": len(good) / len(results) if results else 0.0,
        "goodput_req_per_s": len(good) / duration if duration else 0.0,
        "mean_prompt_tokens": prompt / len(ok) if ok else 0.0,
        "mean_out_tokens": sum(r.out_tokens for r in ok) / len(ok) if ok else 0.0,
        # 캐시 재사용률: 입력 토큰 중 다시 계산하지 않고 캐시에서 가져온 비율 (엔진이 알려 줄 때만)
        "cache_hit_ratio": (sum(cached) / prompt) if cached and prompt else None,
        "token_source": sorted({r.token_source for r in ok}),
    }
