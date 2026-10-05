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
    """MCP 서버를 한 번 띄워 연결을 유지한 채 도구를 쓴다.
    (기본 방식은 도구를 부를 때마다 서버 프로세스를 새로 띄워, 검색 색인을 매번 다시 만든다 — 실험으로 확인.)"""
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
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(base_url=spec["base_url"], model=spec["model"], api_key=spec.get("api_key", "none"),
                      temperature=0.0, max_tokens=spec.get("max_tokens", 512), timeout=spec.get("timeout", 120),
                      default_headers=spec.get("headers"),
                      extra_body={"chat_template_kwargs": {"enable_thinking": False}})   # Qwen3 생각 모드 끔


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
    final = next((str(m.content) for m in reversed(msgs) if isinstance(m, AIMessage) and not m.tool_calls), "")
    usage = [m.usage_metadata for m in msgs if isinstance(m, AIMessage) and getattr(m, "usage_metadata", None)]
    return {"question": question, "tool_calls": calls, "executed": executed, "approvals_asked": asked,
            "answer": final, "llm_calls": sum(1 for m in msgs if isinstance(m, AIMessage)),
            "input_tokens": sum(u.get("input_tokens", 0) for u in usage), "output_tokens": sum(u.get("output_tokens", 0) for u in usage),
            "seconds": elapsed, "error": error}
