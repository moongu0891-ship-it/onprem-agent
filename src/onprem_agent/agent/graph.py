"""LangGraph 에이전트 그래프. 두 시나리오가 같은 코드를 쓰고, 시스템 프롬프트와 도구 서버만 바뀐다.

    [사용자 질문] → agent(모델) ─ 도구 요청 없음 ─┬─ (require_tool) 이번 질문에 도구를 한 번도 안 썼으면 한 번 되돌림 → agent
                       │ 도구 요청                 └─ (auto_cite) finalize: 근거 번호를 코드가 붙임 → 끝
                       ▼
                     gate ─ 승인이 필요한 도구(create_ticket)가 있으면 멈추고 사람에게 묻는다(interrupt)
                       │        └ 거절 → "실행하지 않음" 결과를 붙여 agent 로 돌아감
                       ▼ 승인 · 승인 불필요
                     tools(도구 실행) → agent → …

- 단계 상한(max_steps): 모델이 도구를 끝없이 부르면 멈추고, 지금까지의 결과로 답하게 한다.
- 체크포인터: 대화·승인 대기 상태를 저장한다. 승인을 기다리는 동안 서버가 재시작돼도 이어 갈 수 있다(SQLite·PostgreSQL).
- 도구 실행은 직접 한다(ToolNode 대신): 없는 도구 이름·도구 오류를 모델에게 '오류 결과'로 돌려줘 스스로 고치게 하고,
  MCP 결과(내용 블록 목록)를 엔진이 받는 일반 문자열로 바꾼다.

안전 기능 두 개 — 모델이 자주 틀리는 것은 모델에 맡기지 않고 구조로 보장한다(노트북 1차 측정, 문제해결 이력 D21):
- require_tool: 작은 모델은 번호가 없는 질문에서 도구를 건너뛰고 지어냈다. 이번 질문에 도구를 한 번도 쓰지 않고 답하면
  한 번만 되돌려 "업무 질문이면 먼저 도구를, 인사·잡담이면 같은 답을" 하게 한다.
- auto_cite: 모델은 근거를 1, 2 같은 순번으로 적거나 찾지도 않은 근거를 붙였다. 모델이 쓴 [근거: …] 는 지우고,
  이번 질문에서 성공한 도구 결과의 [대괄호] 번호를 코드가 붙인다. 모델이 쓴 원래 답은 response_metadata["raw_answer"] 에 남긴다.
"""

from __future__ import annotations

import re
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command, interrupt

APPROVAL_TOOLS = frozenset({"create_ticket"})
NUDGE_PREFIX = "nudge-"
NUDGE = ("(시스템 확인) 방금 도구로 근거를 찾지 않고 답했다. 설비 경보·작업 이력·작업 요청, 고객·요금제·약관에 관한 업무 질문이면 "
         "지금 알맞은 도구를 먼저 불러라. 인사·잡담처럼 도구가 필요 없는 말이면 방금 답을 그대로 다시 써라.")
SOURCE_ID = re.compile(r"\[([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)\]")          # [OPS-CRB-06] [WO-00125] [TK-0001] [C0050] [CS-PLN-5G89]
MODEL_CITE = re.compile(r"\[?\s*근거\s*:[^\]\n]*\]?")


class AgentState(MessagesState):
    steps: int


def _to_text(out) -> str:
    if isinstance(out, str):
        return out
    if isinstance(out, (list, tuple)):
        return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in out)
    return str(out)


def is_nudge(m) -> bool:
    return isinstance(m, HumanMessage) and str(m.id or "").startswith(NUDGE_PREFIX)


def this_turn(messages: list) -> list:
    """마지막 '진짜' 사용자 질문(되돌림 메시지 제외) 이후의 메시지."""
    idx = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage) and not is_nudge(m)), default=0)
    return messages[idx:]


def cite_sources(raw: str, turn: list) -> str:
    """모델이 쓴 근거 표기를 지우고, 이번 질문에서 성공한 도구 결과의 근거 번호를 붙인다."""
    ids = []
    for m in turn:
        if isinstance(m, ToolMessage) and m.status == "success":
            ids += [x for x in SOURCE_ID.findall(str(m.content)) if x not in ids]
    text = MODEL_CITE.sub("", raw)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text + (f"\n\n[근거: {', '.join(ids[:6])}]" if ids else "")


def build_graph(model, tools, system_prompt: str, approval_tools=APPROVAL_TOOLS, max_steps: int = 6, checkpointer=None,
                require_tool: bool = False, auto_cite: bool = False):
    by_name = {t.name: t for t in tools}
    llm_tools = model.bind_tools(tools)

    async def agent(state: AgentState):
        steps = state.get("steps", 0)
        msgs = [SystemMessage(system_prompt), *state["messages"]]
        if steps >= max_steps:   # 단계 상한: 도구 없이 지금까지의 결과로 답하게 한다
            msgs.append(SystemMessage("도구를 더 부르지 말고 지금까지의 결과로 답하라."))
            resp = await model.ainvoke(msgs)
        else:
            resp = await llm_tools.ainvoke(msgs)
        out = [resp]
        if require_tool and not resp.tool_calls and steps < max_steps:
            turn = this_turn(state["messages"])
            if not any(isinstance(m, ToolMessage) for m in turn) and not any(is_nudge(m) for m in turn):
                out.append(HumanMessage(NUDGE, id=f"{NUDGE_PREFIX}{uuid.uuid4().hex[:8]}"))
        return {"messages": out, "steps": steps + 1}

    def route(state: AgentState):
        last = state["messages"][-1]
        if is_nudge(last):
            return "agent"
        if isinstance(last, AIMessage) and last.tool_calls:
            return "gate"
        return "finalize" if auto_cite else END

    async def gate(state: AgentState):
        last = state["messages"][-1]
        need = [tc for tc in last.tool_calls if tc["name"] in approval_tools]
        if not need:
            return Command(goto="tools")
        decision = interrupt({"type": "approval", "tool_calls": [{"name": tc["name"], "args": tc["args"]} for tc in need]})
        if isinstance(decision, dict) and decision.get("approved"):
            return Command(goto="tools")
        reason = (decision or {}).get("reason", "") if isinstance(decision, dict) else ""
        msgs = [ToolMessage(content=("승인되지 않아 실행하지 않았다." + (f" 사유: {reason}" if reason else "")
                                     if tc["name"] in approval_tools else "같은 요청의 다른 작업이 승인되지 않아 함께 실행하지 않았다."),
                            tool_call_id=tc["id"], name=tc["name"], status="error") for tc in last.tool_calls]
        return Command(goto="agent", update={"messages": msgs})

    async def run_tools(state: AgentState):
        last = state["messages"][-1]
        out = []
        for tc in last.tool_calls:
            tool = by_name.get(tc["name"])
            if tool is None:
                out.append(ToolMessage(content=f"오류: 그런 도구는 없다: {tc['name']}. 쓸 수 있는 도구: {', '.join(by_name)}",
                                       tool_call_id=tc["id"], name=tc["name"], status="error"))
                continue
            try:
                text = _to_text(await tool.ainvoke(tc["args"]))
                out.append(ToolMessage(content=text, tool_call_id=tc["id"], name=tc["name"],
                                       status="error" if text.startswith("오류") else "success"))
            except Exception as e:  # 인자 형식 오류 등 — 모델이 고쳐서 다시 부를 수 있게 결과로 돌려준다
                out.append(ToolMessage(content=f"오류: {type(e).__name__}: {str(e)[:300]}", tool_call_id=tc["id"],
                                       name=tc["name"], status="error"))
        return {"messages": out}

    async def finalize(state: AgentState):
        last = state["messages"][-1]
        raw = str(last.content)
        text = cite_sources(raw, this_turn(state["messages"]))
        # 같은 id 로 돌려주면 MessagesState 가 마지막 답을 바꿔 끼운다(새로 덧붙이지 않는다)
        return {"messages": [AIMessage(content=text, id=last.id,
                                       response_metadata={**(last.response_metadata or {}), "raw_answer": raw},
                                       usage_metadata=getattr(last, "usage_metadata", None))]}

    g = StateGraph(AgentState)
    g.add_node("agent", agent)
    g.add_node("gate", gate, destinations=("tools", "agent"))
    g.add_node("tools", run_tools)
    g.add_node("finalize", finalize)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, ["gate", "agent", "finalize", END])
    g.add_edge("tools", "agent")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)
