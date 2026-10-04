"""OpenAI 호환 /v1/chat/completions 스트리밍 요청 하나를 보내고 시간을 잰다.

vLLM · SGLang · llama.cpp · LiteLLM 모두 같은 형식이라 한 코드로 잰다.

잰 것
- TTFT  첫 토큰까지 걸린 시간. 사용자가 '반응이 있다'고 느끼는 시점.
- ITL   토큰과 토큰 사이 간격. 스트리밍이 끊겨 보이는지.
- TPOT  첫 토큰 이후 토큰당 평균 시간 = (전체 - TTFT) / (출력 토큰 - 1).
- 캐시 재사용 토큰  앞부분(시스템 프롬프트 등)을 다시 계산하지 않고 캐시에서 가져온 입력 토큰 수.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field


@dataclass
class RequestResult:
    ok: bool
    e2e: float                      # 초
    ttft: float | None = None       # 초
    itl: list[float] = field(default_factory=list)
    out_tokens: int = 0
    prompt_tokens: int | None = None
    cached_tokens: int | None = None
    text: str = ""
    error: str | None = None
    token_source: str = "usage"     # usage: 서버가 센 값 / events: 스트림 조각 수로 셈

    @property
    def tpot(self) -> float | None:
        if self.ttft is None or self.out_tokens < 2:
            return None
        return (self.e2e - self.ttft) / (self.out_tokens - 1)


def _cached_from(chunk: dict) -> int | None:
    """엔진마다 캐시 재사용 토큰을 싣는 자리가 다르다."""
    usage = chunk.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    if details.get("cached_tokens") is not None:          # vLLM(--enable-prompt-tokens-details), SGLang
        return int(details["cached_tokens"])
    timings = chunk.get("timings") or {}
    if timings.get("cache_n") is not None:                 # llama.cpp
        return int(timings["cache_n"])
    return None


async def stream_chat(client, base_url: str, model: str, messages: list[dict], max_tokens: int,
                      extra: dict | None = None, headers: dict | None = None) -> RequestResult:
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.0,
            "stream": True, "stream_options": {"include_usage": True}, **(extra or {})}
    t0 = time.perf_counter()
    first, last, events, itl, parts = None, None, 0, [], []
    usage_out = prompt = cached = None
    try:
        async with client.stream("POST", f"{base_url.rstrip('/')}/chat/completions", json=body,
                                 headers=headers or {}) as resp:
            if resp.status_code != 200:
                msg = (await resp.aread()).decode(errors="replace")[:300]
                return RequestResult(ok=False, e2e=time.perf_counter() - t0, error=f"HTTP {resp.status_code}: {msg}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                now = time.perf_counter()
                for ch in chunk.get("choices") or []:
                    d = ch.get("delta") or {}
                    piece = d.get("content") or d.get("reasoning_content") or ""
                    if piece or d.get("tool_calls"):
                        if first is None:
                            first = now
                        else:
                            itl.append(now - last)
                        last = now
                        events += 1
                        parts.append(piece)
                u = chunk.get("usage")
                if u:
                    usage_out = u.get("completion_tokens", usage_out)
                    prompt = u.get("prompt_tokens", prompt)
                c = _cached_from(chunk)
                if c is not None:
                    cached = c
    except Exception as e:  # 연결 끊김·시간 초과도 '실패한 요청'으로 센다
        return RequestResult(ok=False, e2e=time.perf_counter() - t0, error=f"{type(e).__name__}: {e}"[:300])
    e2e = time.perf_counter() - t0
    return RequestResult(ok=first is not None, e2e=e2e, ttft=(first - t0) if first else None, itl=itl,
                         out_tokens=usage_out if usage_out else events, prompt_tokens=prompt, cached_tokens=cached,
                         text="".join(parts), token_source="usage" if usage_out else "events",
                         error=None if first else "응답에 토큰이 없음")
