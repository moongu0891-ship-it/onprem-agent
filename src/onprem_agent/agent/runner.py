"""에이전트 실행: MCP 서버 연결, 모델 만들기, 과업 하나를 끝까지 돌리고 기록 남기기."""

from __future__ import annotations

import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

ROOT = Path(__file__).resolve().parents[3]


@asynccontextmanager
async def mcp_tools(scenario: str, env: dict | None = None):
    """MCP 서버를 한 번 띄워 연결을 유지한 채 업무 기능(도구)을 쓴다.
    (기본 방식은 업무 기능(도구)을 부를 때마다 서버 프로세스를 새로 띄워, 검색 색인을 매번 다시 만든다 — 실험으로 확인.)"""
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from langchain_mcp_adapters.tools import load_mcp_tools
    e = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "ONPREM_ROOT": str(ROOT), **(env or {})}
    client = MultiServerMCPClient({scenario: {"command": sys.executable, "transport": "stdio", "env": e,
                                              "args": ["-m", "onprem_agent.agent.mcp_servers", scenario]}})
    async with client.session(scenario) as session:
        yield await load_mcp_tools(session)


def make_model(spec: dict, scenario: str):
    """spec: {kind: rule} 또는 {kind: openai, base_url, model, api_key?, headers?}
    OpenAI 호환이면 게이트웨이(LiteLLM agent-llm)든 엔진 직접이든 같은 코드로 부른다."""
    if spec["kind"] == "rule":
        from .rule_model import RuleModel
        return RuleModel(scenario=scenario)
    import httpx
    from langchain_openai import ChatOpenAI
    # 연결(httpx 클라이언트)을 모델마다 새로 만든다. langchain-openai 는 기본 클라이언트를 주소별로 캐시해 두는데,
    # 평가는 모델마다 asyncio.run 을 새로 돌리므로 같은 주소의 두 번째 모델이 닫힌 이벤트 루프의 연결을 물려받아
    # 첫 요청이 "Event loop is closed" 로 실패했다(노트북 2차, 문제해결 이력 D22).
    timeout = spec.get("timeout", 120)
    return ChatOpenAI(base_url=spec["base_url"], model=spec["model"], api_key=spec.get("api_key", "none"),
                      temperature=0.0, max_tokens=spec.get("max_tokens", 512), timeout=timeout,
                      default_headers=spec.get("headers"),
                      http_async_client=httpx.AsyncClient(timeout=timeout), http_client=httpx.Client(timeout=timeout),
                      include_response_headers=bool(spec.get("response_headers", False)),   # 게이트웨이: 어느 엔진이 답했나
                      # Qwen3 생각 모드: 기본 끔(서빙 측정과 같게). spec 에 thinking: true 면 켠다. 생각 글은 엔진 설정에 따라 답에 섞여 올 수 있어
                      # 그래프 finalize 에서 항상 뗀다(strip_think, D25)
                      extra_body={"chat_template_kwargs": {"enable_thinking": bool(spec.get("thinking", False))}})


def _on_backup(m) -> bool:
    from .graph import on_backup
    return on_backup(m)


async def run_task(app, question: str, approval: str = "approve", max_interrupts: int = 3) -> dict:
    """과업 하나를 끝까지 돌린다. approval: 승인 요청이 오면 approve(승인) / reject(거절)."""
    cfg = {"configurable": {"thread_id": f"t-{uuid.uuid4().hex[:10]}"}}
    t0 = time.perf_counter()
    asked = []
    inp = {"messages": [("user", question)]}
    error = None
    try:
        for _ in range(max_interrupts + 1):
            state = await app.ainvoke(inp, cfg)
            intr = state.get("__interrupt__")
            if not intr:
                break
            asked.append(intr[0].value)
            inp = Command(resume={"approved": approval == "approve", "reason": "" if approval == "approve" else "평가: 거절"})
    except Exception as e:   # 모델 호출 실패 등 — 과업 실패로 기록하고 계속
        error = f"{type(e).__name__}: {str(e)[:300]}"
        state = await app.aget_state(cfg)
        state = state.values if state else {"messages": []}
    elapsed = time.perf_counter() - t0
    msgs = state.get("messages", [])
    calls = [{"name": tc["name"], "args": tc["args"]} for m in msgs if isinstance(m, AIMessage) for tc in m.tool_calls]
    executed = [{"name": m.name, "status": m.status, "content": str(m.content)[:400]} for m in msgs if isinstance(m, ToolMessage)]
    last = next((m for m in reversed(msgs) if isinstance(m, AIMessage) and not m.tool_calls), None)
    final = str(last.content) if last else ""
    raw = (last.response_metadata or {}).get("raw_answer", final) if last else ""   # 근거를 코드가 붙였으면 모델이 쓴 원래 답
    usage = [m.usage_metadata for m in msgs if isinstance(m, AIMessage) and getattr(m, "usage_metadata", None)]
    return {"question": question, "tool_calls": calls, "executed": executed, "approvals_asked": asked,
            "answer": final, "raw_answer": raw,
            "backup_calls": sum(1 for m in msgs if isinstance(m, AIMessage) and _on_backup(m)),
            "degraded_notice": bool(last is not None and (last.response_metadata or {}).get("degraded")),
            "nudged": sum(1 for m in msgs if isinstance(m, AIMessage) and (m.response_metadata or {}).get("nudged")),
            "out_of_scope": sum(1 for m in msgs if isinstance(m, AIMessage) and (m.response_metadata or {}).get("out_of_scope")),
            "refusal_respected": sum(1 for m in msgs if isinstance(m, AIMessage) and (m.response_metadata or {}).get("refusal_respected")),
            # 되돌림 직전에 모델이 쓴 답(버려진 답). 되돌림이 무엇을 바꿨는지 실제 답으로 보기 위해 남긴다(6주차 ③)
            "pre_nudge": [m.response_metadata["pre_nudge"] for m in msgs if isinstance(m, AIMessage) and (m.response_metadata or {}).get("pre_nudge")],
            "llm_calls": sum(1 for m in msgs if isinstance(m, AIMessage)),
            "input_tokens": sum(u.get("input_tokens", 0) for u in usage), "output_tokens": sum(u.get("output_tokens", 0) for u in usage),
            "seconds": elapsed, "error": error}
