"""에이전트와 대화하는 데모 (터미널). 작업 요청 티켓처럼 상태를 바꾸는 일은 사람이 y/n 으로 승인한다.

    python scripts/agent_chat.py ops                                   # 규칙 모델 (GPU 없이)
    python scripts/agent_chat.py ops --model sglang                    # SGLang 직접 (localhost:30000)
    python scripts/agent_chat.py cs  --model gateway                   # LiteLLM 게이트웨이의 agent-llm-4b
    python scripts/agent_chat.py ops --model sglang --store postgres   # 대화·승인 대기 상태를 PostgreSQL 에 저장

대화와 '승인 대기' 상태는 체크포인터에 저장된다. --thread 로 같은 번호를 주면 프로그램을 껐다 켜도 이어진다
(승인을 기다리던 중에 껐다면 다시 켤 때 승인을 묻는다).
- sqlite   : var/agent_state.db (기본)
- postgres : 2주차 pgvector 컨테이너의 PostgreSQL (docker compose --profile pgvector up -d) — 벡터 검색과 에이전트 상태를 한 DB 로
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from onprem_agent.agent.graph import build_graph  # noqa: E402
from onprem_agent.agent.prompts import SYSTEM  # noqa: E402
from onprem_agent.agent.runner import make_model, mcp_tools  # noqa: E402

MODELS = {
    "rule": {"kind": "rule"},
    "sglang": {"kind": "openai", "base_url": "http://localhost:30000/v1", "model": "qwen3-1.7b"},
    # 4·5주차 측정으로 고른 기본값: Qwen3-4B + 생각 모드 + 안전 기능 + 안전 질문 검색 (과업 성공 96%)
    "sglang-4b": {"kind": "openai", "base_url": "http://localhost:30000/v1", "model": "qwen3-4b",
                  "thinking": True, "max_tokens": 2048, "timeout": 300},
    "vllm": {"kind": "openai", "base_url": "http://localhost:8000/v1", "model": "qwen3-1.7b"},
    # 5주차 결정: 게이트웨이 이름 agent-llm-4b (Qwen3-4B + 생각 모드, 1순위 장애 시 CPU 대체 → 답에 지연 안내)
    "gateway": {"kind": "openai", "base_url": "http://localhost:4000/v1", "model": "agent-llm-4b", "api_key": "sk-local-dev",
                "thinking": True, "max_tokens": 2048, "timeout": 900, "response_headers": True},
}
PG_DSN = "postgresql://agent:agent@localhost:15432/agent"


async def chat(scenario, model_key, store, thread, embedder):
    from langchain_core.messages import AIMessage
    from langgraph.types import Command
    if store == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver as Saver
        conn = PG_DSN
    else:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver as Saver
        (ROOT / "var").mkdir(exist_ok=True)
        conn = str(ROOT / "var/agent_state.db")
    async with Saver.from_conn_string(conn) as saver, mcp_tools(scenario, {"ONPREM_EMBEDDER": json.dumps(embedder)}) as tools:
        if store == "postgres":
            await saver.setup()
        app = build_graph(make_model(MODELS[model_key], scenario), tools, SYSTEM[scenario], checkpointer=saver,
                          require_tool=True, auto_cite=True, safety_search=True,
                          degraded_notice=model_key == "gateway")   # 4·5주차 측정으로 켠 기능들
        cfg = {"configurable": {"thread_id": thread}}
        print(f"[{scenario} · {model_key} · 저장 {store} · 대화 번호 {thread}]  업무 기능(도구): {', '.join(t.name for t in tools)}  (끝내려면 빈 줄)")
        pending = (await app.aget_state(cfg)).interrupts
        inp = None
        while True:
            if pending:                                     # 승인 대기 — 사람에게 묻는다
                for tc in pending[0].value["tool_calls"]:
                    print(f"  ⚠ 승인 필요: {tc['name']}({json.dumps(tc['args'], ensure_ascii=False)})")
                ok = input("  실행할까요? [y/N] ").strip().lower() == "y"
                inp = Command(resume={"approved": ok, "reason": "" if ok else "담당자가 거절"})
            else:
                q = input("\n질문> ").strip()
                if not q:
                    break
                inp = {"messages": [("user", q)]}
            state = await app.ainvoke(inp, cfg)
            pending = state.get("__interrupt__")
            if not pending:
                for m in state["messages"][-6:]:
                    if isinstance(m, AIMessage) and m.tool_calls:
                        print("  · 업무 기능(도구):", ", ".join(f"{tc['name']}({json.dumps(tc['args'], ensure_ascii=False)})" for tc in m.tool_calls))
                print("\n" + str(state["messages"][-1].content))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=["ops", "cs"])
    ap.add_argument("--model", default="rule", choices=list(MODELS))
    ap.add_argument("--store", default="sqlite", choices=["sqlite", "postgres"])
    ap.add_argument("--thread", default=None, help="대화 번호 (같은 번호면 이어서)")
    ap.add_argument("--embedder", default='{"kind": "hash"}', help='검색 임베더 JSON, 예: \'{"kind":"sentence-transformers","model":"BAAI/bge-m3"}\'')
    a = ap.parse_args()
    asyncio.run(chat(a.scenario, a.model, a.store, a.thread or uuid.uuid4().hex[:8], json.loads(a.embedder)))


if __name__ == "__main__":
    main()
