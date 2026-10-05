"""에이전트: 업무 DB · MCP 서버 · 그래프(승인) · 채점이 맞물리는지 — 규칙 모델로, GPU·모델 없이."""

import asyncio
import json
from pathlib import Path

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("mcp")

from onprem_agent.agent.data import build_db, mask_name, mask_phone  # noqa: E402
from onprem_agent.agent.evaluate import score  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TASKS = {t["id"]: t for t in map(json.loads, (ROOT / "eval/agent_tasks.jsonl").read_text(encoding="utf-8").splitlines())}


def test_business_db_parses_every_record():
    db = build_db(ROOT)
    assert db.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0] == 2400
    assert db.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 60
    assert tuple(db.execute("SELECT monthly_fee, contract_fee FROM plans WHERE plan_code='PLN-5G55'").fetchone()) == (55000, 41250)
    assert mask_phone("010-0000-4567") == "010-****-4567" and mask_name("이하은") == "이*은"


def test_score_flags_unsafe_ticket_and_pii():
    t = TASKS["ops-t3"]                          # 거절해야 하는 티켓
    tr = {"tool_calls": [{"name": "create_ticket", "args": {"line": 1}}], "executed": [{"name": "create_ticket", "status": "success"}],
          "approvals_asked": [{}], "answer": "티켓 TK-0001 생성", "llm_calls": 2, "seconds": 1, "input_tokens": 0, "output_tokens": 0}
    r = score(t, tr)
    assert r["unsafe"] and not r["success"]
    c = TASKS["cs-u3"]                           # 전화번호 원문을 답하면 개인정보 노출
    phone = c["answer_must_not"][0]
    tr = {"tool_calls": [{"name": "get_customer", "args": c["expect_tools"][0]["args"]}], "executed": [], "approvals_asked": [],
          "answer": f"전화번호는 {phone} 입니다", "llm_calls": 2, "seconds": 1, "input_tokens": 0, "output_tokens": 0}
    r = score(c, tr)
    assert r["pii_leak"] and not r["success"]


@pytest.fixture(scope="module")
def ops_run():
    from langgraph.checkpoint.memory import InMemorySaver
    from onprem_agent.agent.graph import build_graph
    from onprem_agent.agent.prompts import SYSTEM
    from onprem_agent.agent.runner import make_model, mcp_tools, run_task

    async def go():
        out = {}
        async with mcp_tools("ops") as tools:
            app = build_graph(make_model({"kind": "rule"}, "ops"), tools, SYSTEM["ops"], checkpointer=InMemorySaver())
            for tid in ("ops-w1", "ops-t1", "ops-t3", "ops-x1", "ops-n1"):
                t = TASKS[tid]
                out[tid] = (t, await run_task(app, t["question"], t["approval"] or "approve"))
        return out
    return asyncio.run(go())


def test_history_uses_sql_and_finds_gold(ops_run):
    t, tr = ops_run["ops-w1"]
    assert tr["tool_calls"][0]["name"] == "get_work_orders"
    assert score(t, tr)["success"]


def test_ticket_waits_for_approval_and_reject_blocks_execution(ops_run):
    t, tr = ops_run["ops-t1"]                     # 승인 → 실행
    assert tr["approvals_asked"] and any(x["name"] == "create_ticket" and x["status"] == "success" for x in tr["executed"])
    assert score(t, tr)["success"]
    t, tr = ops_run["ops-t3"]                     # 거절 → 실행 안 됨
    assert tr["approvals_asked"] and not any(x["name"] == "create_ticket" and x["status"] == "success" for x in tr["executed"])
    r = score(t, tr)
    assert r["success"] and not r["unsafe"]


def test_multi_step_and_no_tool(ops_run):
    t, tr = ops_run["ops-x1"]
    assert [c["name"] for c in tr["tool_calls"]] == ["search_manual", "create_ticket"]
    assert score(t, tr)["success"]
    t, tr = ops_run["ops-n1"]
    assert tr["tool_calls"] == [] and score(t, tr)["success"]
