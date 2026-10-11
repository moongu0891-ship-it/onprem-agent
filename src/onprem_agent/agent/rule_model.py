"""규칙 기반 '모델' (핵심) — LLM 없이 창구의 규칙(창구 폴더의 rules.py)으로 업무 기능(도구)을 고르고, 결과를 이어 붙여 답한다.

쓰임
1. 모듈 시험·CI: GPU 없이 그래프·MCP 서버·승인 절차·평가 하네스가 맞물리는지 확인한다.
2. 기준선: "LLM 에이전트가 정해진 규칙보다 나은가"를 같은 과업 평가셋으로 잰다.
   규칙은 문장을 이해하지 못하므로 바꿔 말한 질문·여러 단계가 얽힌 질문에서 약하다 — 그 차이가 LLM 을 쓰는 이유다.

창구의 rules.py 는 first_calls(q, call) · next_calls(q, text, done, call) · CITE 를 두고, 인사 답 GREETING 을 둘 수 있다.
"""

from __future__ import annotations

import importlib.util
import re
import uuid
from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .desk import load_desk

GREETING = re.compile(r"\s*(안녕|고마워|감사)[^?]{0,20}")
GREETING_ANSWER = "안녕하세요. 설비 경보·작업 이력·작업 요청(또는 고객·요금제·약관)에 대해 물어보세요."


def _call(name, args):
    return {"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}", "type": "tool_call"}


@lru_cache(maxsize=None)
def _rules(desk_name: str):
    path = load_desk(desk_name).rules
    spec = importlib.util.spec_from_file_location(f"desk_rules_{desk_name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RuleModel(BaseChatModel):
    scenario: str = "ops"            # 창구 이름
    tool_names: tuple = ()

    @property
    def _llm_type(self) -> str:
        return "rule"

    def bind_tools(self, tools, **kwargs):
        names = tuple(t["function"]["name"] if isinstance(t, dict) else t.name for t in tools)
        return self.model_copy(update={"tool_names": names})

    def _answer(self, tool_msgs: list[ToolMessage]) -> str:
        if not tool_msgs:
            return getattr(_rules(self.scenario), "GREETING", GREETING_ANSWER)
        cite_re = _rules(self.scenario).CITE
        parts, cites = [], []
        for m in tool_msgs:
            t = str(m.content)
            if t.startswith("승인되지 않아"):
                parts.append("작업 요청은 승인되지 않아 실행하지 않았습니다.")
                continue
            parts.append(t[:600])
            cites += [c for c in cite_re.findall(t) if c not in cites]
        out = "도구 조회 결과입니다.\n" + "\n".join(parts)
        return out + (f"\n[근거: {', '.join(cites[:3])}]" if cites else "")

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        # 이번 질문 이후의 업무 기능(도구) 결과만 본다
        idx = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
        q = str(messages[idx].content)
        tool_msgs = [m for m in messages[idx:] if isinstance(m, ToolMessage)]
        done = {m.name for m in tool_msgs}
        if self.tool_names:
            rules = _rules(self.scenario)
            if not tool_msgs:
                calls = [] if GREETING.fullmatch(q) else rules.first_calls(q, _call)
            else:
                calls = rules.next_calls(q, "\n".join(str(m.content) for m in tool_msgs), done, _call)
            calls = [c for c in calls if c["name"] in self.tool_names]
            if calls:
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=calls))])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self._answer(tool_msgs)))])
