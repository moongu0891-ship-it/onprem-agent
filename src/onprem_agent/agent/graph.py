"""LangGraph 에이전트 그래프. 두 시나리오가 같은 코드를 쓰고, 시스템 프롬프트와 도구 서버만 바뀐다.

    [사용자 질문] → agent(모델) ─ 도구 요청 없음 → 끝
                       │ 도구 요청
                       ▼
                     gate ─ 승인이 필요한 도구(create_ticket)가 있으면 멈추고 사람에게 묻는다(interrupt)
                       │        └ 거절 → "실행하지 않음" 결과를 붙여 agent 로 돌아감
                       ▼ 승인 · 승인 불필요
                     tools(도구 실행) → agent → …

- 단계 상한(max_steps): 모델이 도구를 끝없이 부르면 멈추고, 지금까지의 결과로 답하게 한다.
- 체크포인터: 대화·승인 대기 상태를 저장한다. 승인을 기다리는 동안 서버가 재시작돼도 이어 갈 수 있다(SQLite·PostgreSQL).
- 도구 실행은 직접 한다(ToolNode 대신): 없는 도구 이름·도구 오류를 모델에게 '오류 결과'로 돌려줘 스스로 고치게 하고,
  MCP 결과(내용 블록 목록)를 엔진이 받는 일반 문자열로 바꾼다.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command, interrupt

APPROVAL_TOOLS = frozenset({"create_ticket"})


class AgentState(MessagesState):
    steps: int


def _to_text(out) -> str:
    if isinstance(out, str):
        return out
    if isinstance(out, (list, tuple)):
        return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in out)
    return str(out)


def build_graph(model, tools, system_prompt: str, approval_tools=APPROVAL_TOOLS, max_steps: int = 6, checkpointer=None):
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
        return {"messages": [resp], "steps": steps + 1}

    def route(state: AgentState):
        last = state["messages"][-1]
        return "gate" if isinstance(last, AIMessage) and last.tool_calls else END

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

    g = StateGraph(AgentState)
    g.add_node("agent", agent)
    g.add_node("gate", gate, destinations=("tools", "agent"))
    g.add_node("tools", run_tools)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, ["gate", END])
    g.add_edge("tools", "agent")
    return g.compile(checkpointer=checkpointer)
