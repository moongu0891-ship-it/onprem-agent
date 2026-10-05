"""LangGraph 에이전트 그래프. 두 시나리오가 같은 코드를 쓰고, 시스템 프롬프트와 업무 기능(도구) 서버만 바뀐다.

    [사용자 질문] → agent(모델) ─ 업무 기능(도구) 요청 없음 ─┬─ (안전 기능 ① 되돌림) 이번 질문에 업무 기능(도구)을 한 번도 안 썼으면,
                       │ 업무 기능(도구) 요청                │    업무 기능(도구) 선택을 '필수'로 걸고 한 번 더 묻는다 — 업무 기능(도구) 또는 no_tool_needed(인사·잡담)
                       │                          └─ (안전 기능 ② 근거 자동) finalize: 근거 번호를 코드가 붙임 → 끝
                       ▼
                     gate ─ 승인이 필요한 업무 기능(도구)(create_ticket)가 있으면 멈추고 사람에게 묻는다(interrupt)
                       │        └ 거절 → "실행하지 않음" 결과를 붙여 agent 로 돌아감
                       ▼ 승인 · 승인 불필요
                     tools(업무 기능(도구) 실행) → agent → …

- 단계 상한(max_steps): 모델이 업무 기능(도구)을 끝없이 부르면 멈추고, 지금까지의 결과로 답하게 한다.
- 체크포인터: 대화·승인 대기 상태를 저장한다. 승인을 기다리는 동안 서버가 재시작돼도 이어 갈 수 있다(SQLite·PostgreSQL).
- 업무 기능(도구) 실행은 직접 한다(ToolNode 대신): 없는 업무 기능(도구) 이름·업무 기능(도구) 오류를 모델에게 '오류 결과'로 돌려줘 스스로 고치게 하고,
  MCP 결과(내용 블록 목록)를 엔진이 받는 일반 문자열로 바꾼다.

안전 기능 두 개 — 모델이 자주 틀리는 것은 모델에 맡기지 않고 구조로 보장한다(노트북 측정, 문제해결 이력 D21·D23):
- require_tool(되돌림): 작은 모델은 번호가 없는 질문에서 업무 기능(도구)을 건너뛰고 지어냈다. 이번 질문에 업무 기능(도구)을 한 번도 쓰지 않고 답하면
  업무 기능(도구) 선택을 필수(tool_choice="required")로 걸고 한 번 더 묻는다. 인사·잡담이면 no_tool_needed 를 고르게 해 원래 답을 그대로 쓴다.
  (2차에서는 "업무 기능(도구)을 먼저 써라"는 글을 덧붙였는데, 모델이 그 글에 글로 대답할 뿐 업무 기능(도구)을 부르지 않았다 — 4B 13번 되돌려 업무 기능(도구) 호출 0번 증가.)
- auto_cite(근거 자동): 모델은 근거를 1, 2 같은 순번으로 적거나 찾지도 않은 근거를 붙였다. 모델이 쓴 [근거: …] 는 지우고,
  이번 질문에서 성공한 업무 기능(도구) 결과의 [대괄호] 번호를 코드가 붙인다. 모델이 쓴 원래 답은 response_metadata["raw_answer"] 에 남긴다.
"""

from __future__ import annotations

import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command, interrupt

APPROVAL_TOOLS = frozenset({"create_ticket"})
NO_TOOL = "no_tool_needed"
NO_TOOL_SPEC = {"type": "function", "function": {
    "name": NO_TOOL,
    "description": "인사·감사·잡담처럼 업무 도구가 전혀 필요 없는 말일 때만 고른다. 설비·이력·작업 요청·고객·요금제·약관에 관한 질문이면 고르지 않는다.",
    "parameters": {"type": "object", "properties": {}}}}
FORCE_NOTE = ("방금 도구 없이 답하려 했다. 업무 질문이면 알맞은 업무 도구를 골라 불러라. "
              "인사·잡담처럼 도구가 정말 필요 없을 때만 no_tool_needed 를 골라라.")
DEGRADED_NOTICE = ("※ 지금은 대체 엔진으로 답하고 있어 평소보다 느리고 정확도가 낮을 수 있습니다. "
                   "작업 요청처럼 중요한 일은 내용을 한 번 더 확인해 주세요.")
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


def this_turn(messages: list) -> list:
    """마지막 사용자 질문 이후의 메시지."""
    idx = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=0)
    return messages[idx:]


# 안전 질문: 사람이 다칠 수 있는 작업을 묻는 말. 이런 질문은 모델에 맡기지 않고 매뉴얼 검색을 먼저 한다(5주차 safety_search).
# 프롬프트 규칙으로 부탁했을 때 4B 는 매뉴얼 대신 작업 이력을 찾았고 1.7B 는 아무것도 찾지 않았다(D26).
SAFETY_Q = re.compile(r"감전|전원\s*(을\s*)?(차단|끄|내리)|잠금|LOTO|잔압|화상|고온|끼임|회전부|안전\s*(수칙|조치)|다치지|사고\s*안")
THINK = re.compile(r"<think>.*?(</think>|\Z)", re.S)


def strip_think(text: str) -> tuple[str, str]:
    """답에서 생각 글(<think>…</think>)을 떼어 낸다 → (답, 생각 글).
    엔진의 생각 글 분리기(reasoning parser)가 켜져 있지 않으면 생각 글이 답 본문에 그대로 섞여 온다(5주차 발견, D25).
    엔진 설정에 기대지 않고 여기서 항상 뗀다. 닫는 태그 없이 길이 한도에서 끊긴 생각 글도 뗀다."""
    thoughts = "\n".join(m.group(0) for m in THINK.finditer(text))
    return THINK.sub("", text).strip(), thoughts


def on_backup(msg) -> bool:
    """게이트웨이(LiteLLM) 응답 헤더로 대체 엔진이 답했는지 본다(모델에 response_headers 를 켰을 때만 헤더가 있다).
    x-litellm-model-group 이 '-backup' 으로 끝나거나, 대체를 시도한 횟수가 있으면 대체 엔진이다(3주차 장애 대체 시험에서 확인한 헤더)."""
    h = {str(k).lower(): str(v) for k, v in ((getattr(msg, "response_metadata", None) or {}).get("headers") or {}).items()}
    try:
        tried = int(h.get("x-litellm-attempted-fallbacks", "0") or 0)
    except ValueError:
        tried = 0
    return h.get("x-litellm-model-group", "").endswith("-backup") or tried > 0


def cite_sources(raw: str, turn: list) -> str:
    """모델이 쓴 근거 표기를 지우고, 이번 질문에서 성공한 업무 기능(도구) 결과의 근거 번호를 붙인다."""
    ids = []
    for m in turn:
        if isinstance(m, ToolMessage) and m.status == "success":
            ids += [x for x in SOURCE_ID.findall(str(m.content)) if x not in ids]
    text = MODEL_CITE.sub("", raw)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text + (f"\n\n[근거: {', '.join(ids[:6])}]" if ids else "")


def build_graph(model, tools, system_prompt: str, approval_tools=APPROVAL_TOOLS, max_steps: int = 6, checkpointer=None,
                require_tool: bool = False, auto_cite: bool = False, after_tool_model=None, degraded_notice: bool = False,
                safety_search: bool = False):
    """after_tool_model: 이번 질문에 업무 기능(도구) 결과가 하나라도 생긴 뒤에 쓸 모델(5주차 '생각은 첫 단계만').
    생각 모드는 '무엇을 찾을지' 고를 때 효과가 크고(4주차: 54% → 92%), 찾은 결과를 읽고 답을 쓸 때는 시간만 든다는 가정을 잰다.
    결과를 본 뒤에도 업무 기능(도구)을 더 부를 수 있다(여러 단계 과업) — 그때는 생각 없이 고른다."""
    by_name = {t.name: t for t in tools}
    llm_tools = model.bind_tools(tools)
    llm_after = after_tool_model.bind_tools(tools) if after_tool_model is not None else None
    llm_forced = model.bind_tools([*tools, NO_TOOL_SPEC], tool_choice="required") if require_tool else None

    async def agent(state: AgentState):
        steps = state.get("steps", 0)
        msgs = [SystemMessage(system_prompt), *state["messages"]]
        if steps >= max_steps:   # 단계 상한: 업무 기능(도구) 없이 지금까지의 결과로 답하게 한다
            msgs.append(SystemMessage("도구를 더 부르지 말고 지금까지의 결과로 답하라."))
            return {"messages": [await model.ainvoke(msgs)], "steps": steps + 1}
        turn = this_turn(state["messages"])
        has_results = any(isinstance(m, ToolMessage) for m in turn)
        if safety_search and "search_manual" in by_name and not has_results and turn and SAFETY_Q.search(str(turn[0].content)):
            # 안전 질문: 모델을 부르기 전에 매뉴얼 검색부터 — 결과를 본 모델이 그 절차대로 답한다(구조로 보장)
            call = {"name": "search_manual", "args": {"query": str(turn[0].content)}, "id": f"safety_{steps}", "type": "tool_call"}
            return {"messages": [AIMessage(content="", tool_calls=[call], response_metadata={"safety_search": True})],
                    "steps": steps + 1}
        resp = await (llm_after if (llm_after is not None and has_results) else llm_tools).ainvoke(msgs)
        if require_tool and not resp.tool_calls and not any(isinstance(m, ToolMessage) for m in this_turn(state["messages"])):
            # 되돌림: 업무 기능(도구) 선택을 필수로 걸고 한 번 더. 업무 기능(도구)을 고르면 그걸 쓰고(먼저 쓴 답은 버림),
            # no_tool_needed 를 고르거나 아무것도 안 고르면 먼저 쓴 답을 그대로 쓴다.
            forced = await llm_forced.ainvoke([*msgs, SystemMessage(FORCE_NOTE)])
            calls = [tc for tc in forced.tool_calls if tc["name"] != NO_TOOL]
            meta = {**(resp.response_metadata or {}), "nudged": True}
            if calls:
                resp = AIMessage(content="", tool_calls=calls, id=forced.id, response_metadata=meta,
                                 usage_metadata=getattr(forced, "usage_metadata", None))
            else:
                resp = AIMessage(content=resp.content, id=resp.id, response_metadata=meta,
                                 usage_metadata=getattr(resp, "usage_metadata", None))
        return {"messages": [resp], "steps": steps + 1}

    def route(state: AgentState):
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "gate"
        return "finalize"   # 생각 글 떼기·근거 자동·지연 안내는 모두 finalize 에서

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
        raw, thoughts = strip_think(str(last.content))   # 사용자에게도, 채점에도 생각 글은 넣지 않는다
        turn = this_turn(state["messages"])
        text = cite_sources(raw, turn) if auto_cite else raw
        degraded = degraded_notice and any(on_backup(m) for m in turn if isinstance(m, AIMessage))
        if degraded:   # 5주차: 대체 엔진(CPU)이 답했으면 사용자에게 알린다 — '끊기지 않음'과 '같은 품질'은 다르다(3주차)
            text = f"{text}\n\n{DEGRADED_NOTICE}"
        # 같은 id 로 돌려주면 MessagesState 가 마지막 답을 바꿔 끼운다(새로 덧붙이지 않는다)
        return {"messages": [AIMessage(content=text, id=last.id,
                                       response_metadata={**(last.response_metadata or {}), "raw_answer": raw, "degraded": degraded,
                                                          "thinking_chars": len(thoughts)},
                                       usage_metadata=getattr(last, "usage_metadata", None))]}

    g = StateGraph(AgentState)
    g.add_node("agent", agent)
    g.add_node("gate", gate, destinations=("tools", "agent"))
    g.add_node("tools", run_tools)
    g.add_node("finalize", finalize)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, ["gate", "finalize"])
    g.add_edge("tools", "agent")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)
