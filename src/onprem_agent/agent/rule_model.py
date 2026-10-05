"""규칙 기반 '모델' — LLM 없이 정규식과 낱말로 도구를 고르고, 도구 결과를 이어 붙여 답한다.

쓰임
1. CI·테스트: GPU 없이 그래프·MCP 서버·승인 절차·평가 하네스가 맞물리는지 확인한다.
2. 기준선: "LLM 에이전트가 정해진 규칙보다 나은가"를 같은 과업 평가셋으로 잰다.
   규칙은 문장을 이해하지 못하므로 바꿔 말한 질문·여러 단계가 얽힌 질문에서 약하다 — 그 차이가 LLM 을 쓰는 이유다.
"""

from __future__ import annotations

import re
import uuid

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

ALARM = re.compile(r"\b([A-Z]{3}-\d{2})\b")
ERR = re.compile(r"\bERR-\d{3}\b")
LINE = re.compile(r"(\d)\s*호기")
MONTH = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월")
CUST = re.compile(r"\b(C\d{4})\b", re.I)
PLAN = re.compile(r"\b(PLN-[A-Z0-9]{4})\b", re.I)
CITE = re.compile(r"\[((?:OPS|CS|ERR|FAQ)-[A-Z0-9-]+|ERR-\d{3})\]")


def _call(name, args):
    return {"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}", "type": "tool_call"}


def _priority(q: str) -> str:
    if re.search(r"급하지 않|천천히|여유", q):
        return "low"
    if re.search(r"긴급|빨리|급해|최대한 빨리|즉시", q):
        return "high"
    return "normal"


class RuleModel(BaseChatModel):
    scenario: str = "ops"
    tool_names: tuple = ()

    @property
    def _llm_type(self) -> str:
        return "rule"

    def bind_tools(self, tools, **kwargs):
        return self.model_copy(update={"tool_names": tuple(t.name for t in tools)})

    # ── 첫 질문에서 부를 도구 ──
    def _first_calls(self, q: str) -> list[dict]:
        if re.fullmatch(r"\s*(안녕|고마워|감사)[^?]{0,20}", q):
            return []
        if self.scenario == "cs":
            calls = []
            if m := CUST.search(q):
                calls.append(_call("get_customer", {"customer_id": m.group(1).upper()}))
            if m := PLAN.search(q):
                calls.append(_call("get_plan", {"plan_code": m.group(1).upper()}))
            return calls or [_call("search_terms", {"query": q})]
        alarm = ALARM.search(q)
        wants_ticket = re.search(r"티켓|작업 요청|요청 등록|요청 올려|등록해", q)
        line = LINE.search(q)
        if alarm and re.search(r"이력|기록|내역|했었|처리한|건은", q) and not wants_ticket:
            args = {"alarm_code": alarm.group(1)}
            if line:
                args["line"] = int(line.group(1))
            if m := MONTH.search(q):
                args["month"] = f"{m.group(1)}-{int(m.group(2)):02d}"
            return [_call("get_work_orders", args)]
        if wants_ticket and alarm and line:
            ticket = _call("create_ticket", {"line": int(line.group(1)), "alarm_code": alarm.group(1),
                                             "summary": f"{line.group(1)}호기 {alarm.group(1)} 경보 점검 요청", "priority": _priority(q)})
            if re.search(r"조치|방법|순서|알려", q):       # 조치 안내 + 티켓: 검색 먼저, 티켓은 다음 단계에서
                return [_call("search_manual", {"query": alarm.group(1) + " 조치 순서"})]
            return [ticket]
        return [_call("search_manual", {"query": q})]

    # ── 도구 결과를 보고 한 단계 더 갈지 ──
    def _next_calls(self, q: str, tool_msgs: list[ToolMessage], done: set[str]) -> list[dict]:
        text = "\n".join(str(m.content) for m in tool_msgs)
        if self.scenario == "cs" and "get_customer" in done and "get_plan" not in done and re.search(r"요금|얼마|월", q):
            if m := re.search(r"요금제 (PLN-[A-Z0-9]{4})", text):
                return [_call("get_plan", {"plan_code": m.group(1)})]
        if self.scenario == "ops" and "search_manual" in done and "create_ticket" not in done \
                and re.search(r"티켓|작업 요청|요청 등록|요청 올려|등록해", q):
            alarm, line = ALARM.search(q), LINE.search(q)
            if alarm and line:
                return [_call("create_ticket", {"line": int(line.group(1)), "alarm_code": alarm.group(1),
                                                "summary": f"{line.group(1)}호기 {alarm.group(1)} 경보 점검 요청", "priority": _priority(q)})]
        return []

    def _answer(self, tool_msgs: list[ToolMessage]) -> str:
        if not tool_msgs:
            return "안녕하세요. 설비 경보·작업 이력·작업 요청(또는 고객·요금제·약관)에 대해 물어보세요."
        parts, cites = [], []
        for m in tool_msgs:
            t = str(m.content)
            if t.startswith("승인되지 않아"):
                parts.append("작업 요청은 승인되지 않아 실행하지 않았습니다.")
                continue
            parts.append(t[:600])
            cites += [c for c in CITE.findall(t) if c not in cites]
        out = "도구 조회 결과입니다.\n" + "\n".join(parts)
        return out + (f"\n[근거: {', '.join(cites[:3])}]" if cites else "")

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        q = next(str(m.content) for m in reversed(messages) if isinstance(m, HumanMessage))
        # 이번 질문 이후의 도구 결과만 본다
        idx = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
        tool_msgs = [m for m in messages[idx:] if isinstance(m, ToolMessage)]
        done = {m.name for m in tool_msgs}
        if self.tool_names:
            calls = self._first_calls(q) if not tool_msgs else self._next_calls(q, tool_msgs, done)
            calls = [c for c in calls if c["name"] in self.tool_names]
            if calls:
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=calls))])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self._answer(tool_msgs)))])
