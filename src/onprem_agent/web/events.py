"""에이전트 그래프가 한 단계씩 내놓는 결과를 화면용 사건(event)으로 바꾼다.

화면은 업무 기능(도구) 이름·내부 용어 대신 사람이 읽는 말을 보여 준다. 창구마다 다른 말은 창구 정의(desk.yaml 의 ui)에서 온다.
사건 종류
- step      'AI가 처리한 순서'의 칸 하나: {label, value, state}  state = ok | skip | wait | stop
- tool      AI 가 찾아본 자료 하나: {label, query(넣은 값), ids(결과의 [번호]), text, ok}
- approval  담당자 확인 카드: {title, button, fields:[{k, v}], tools:[이름]}
- answer    답: {text, cites, guard, degraded}
"""

from __future__ import annotations

import re

from langchain_core.messages import AIMessage, ToolMessage

from ..agent.graph import DEGRADED_NOTICE

SOURCE_ID = re.compile(r"\[([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)\]")
CITE_LINE = re.compile(r"\n*\[근거:\s*([^\]\n]*)\]\s*")
GUARD_WORDS = {"전화번호 가림": "전화번호를 가림", "주민등록번호 가림": "주민등록번호를 가림", "시스템 지시문 차단": "내부 설정 유출을 막음"}


def tool_label(desk, name: str) -> str:
    return (desk.ui.get("tools") or {}).get(name, name)


def first_arg(args: dict) -> str:
    """업무 기능(도구)에 넣은 값 중 사람이 알아볼 것 하나 (검색어·번호)."""
    for v in (args or {}).values():
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v)
    return ""


def approval_event(desk, tool_calls: list[dict]) -> dict:
    ui = desk.ui.get("approvals") or {}
    names = [tc["name"] for tc in tool_calls]
    first = ui.get(names[0], {}) if names else {}
    fields = []
    for tc in tool_calls:
        conf = ui.get(tc["name"], {})
        labels, values, suffix = conf.get("fields") or {}, conf.get("values") or {}, conf.get("suffix") or {}
        keys = list(labels) or list(tc["args"])
        for k in keys:
            if k not in tc["args"]:
                continue
            v = tc["args"][k]
            v = (values.get(k) or {}).get(str(v), v)
            fields.append({"k": labels.get(k, k), "v": f"{v}{suffix.get(k, '')}"})
    return {"type": "approval", "title": first.get("title") or f"{', '.join(tool_label(desk, n) for n in names)}을(를) 실행하려고 합니다",
            "button": first.get("button") or "승인하고 실행", "done": first.get("done") or "승인하셔서 실행했습니다",
            "fields": fields, "tools": names}


def split_answer(text: str) -> tuple[str, list[str]]:
    """코드가 붙인 [근거: …] 줄을 떼어 출처 목록으로."""
    cites = []
    m = None
    for m in CITE_LINE.finditer(text):
        pass
    if m:
        cites = [c.strip() for c in m.group(1).split(",") if c.strip()]
        text = (text[:m.start()] + "\n\n" + text[m.end():]).strip()
    return text, cites


class TurnTracker:
    """질문 하나를 처리하는 동안 그래프 사건을 받아 화면 사건을 만든다."""

    def __init__(self, desk):
        self.desk = desk
        self.decisions = 0          # AI 가 다음 할 일을 정한 횟수
        self.asked = False          # 이번 질문에 담당자 확인이 있었나
        self.calls = {}             # 업무 기능(도구) 요청 id → 넣은 값

    def start(self, question: str) -> list[dict]:
        pat = self.desk.graph_kwargs()["safety_pattern"]
        hit = bool(pat and pat.search(question))
        return [{"type": "step", "label": "위험 작업 확인", "value": "매뉴얼부터 확인" if hit else "해당 없음",
                 "state": "ok" if hit else "skip"}]

    def resumed(self, approved: bool) -> list[dict]:
        self.asked = True
        return [{"type": "step", "label": "담당자 확인", "value": "승인됨" if approved else "취소됨 · 실행 안 함",
                 "state": "ok" if approved else "stop"}]

    def on_update(self, node: str, update) -> list[dict]:
        out = []
        if node == "__interrupt__":
            self.asked = True
            for intr in update:
                v = getattr(intr, "value", None) or {}
                if v.get("type") == "approval":
                    out.append({"type": "step", "label": "담당자 확인", "value": "확인 기다리는 중", "state": "wait"})
                    out.append(approval_event(self.desk, v.get("tool_calls") or []))
            return out
        msgs = (update or {}).get("messages") or [] if isinstance(update, dict) else []
        for m in msgs:
            meta = getattr(m, "response_metadata", None) or {}
            if node == "agent" and isinstance(m, AIMessage):
                self.calls.update({tc["id"]: tc.get("args") or {} for tc in m.tool_calls})
                if meta.get("claim_check"):
                    out.append({"type": "step", "label": "다시 확인", "value": "하지 않은 일을 했다고 답해서 되돌림", "state": "ok"})
                if meta.get("nudged"):
                    out.append({"type": "step", "label": "다시 찾아보기", "value": "찾아보지 않고 답하려 해서 되돌림", "state": "ok"})
                if m.tool_calls and not meta.get("safety_search"):
                    names = ", ".join(dict.fromkeys(tool_label(self.desk, tc["name"]) for tc in m.tool_calls))
                    label = "질문 이해" if self.decisions == 0 else "다음 할 일"
                    value = f"{names}" + (" (글로 쓴 요청을 살림)" if meta.get("text_tool_call") else "")
                    out.append({"type": "step", "label": label, "value": value, "state": "ok"})
                    self.decisions += 1
            elif node == "tools" and isinstance(m, ToolMessage):
                text = str(m.content)
                ids = list(dict.fromkeys(SOURCE_ID.findall(text)))
                ok = m.status == "success"
                value = (", ".join(ids[:2]) + (" 외" if len(ids) > 2 else "")) if ids else ("결과 없음" if ok else "오류")
                if meta.get("injection_removed"):
                    value += " · 숨은 명령 지움"
                out.append({"type": "step", "label": tool_label(self.desk, m.name), "value": value, "state": "ok" if ok else "stop"})
                out.append({"type": "tool", "label": tool_label(self.desk, m.name), "query": first_arg(self.calls.get(m.tool_call_id)),
                            "ids": ids[:6], "text": text[:700], "ok": ok})
            elif node == "finalize" and isinstance(m, AIMessage):
                body, cites = split_answer(str(m.content).replace(DEGRADED_NOTICE, "").strip())
                acts = meta.get("answer_guard") or []
                if not self.asked:
                    out.append({"type": "step", "label": "담당자 확인", "value": "필요 없음", "state": "skip"})
                out.append({"type": "step", "label": "출처 붙이기", "value": ", ".join(cites) if cites else "찾아본 자료 없음",
                            "state": "ok" if cites else "skip"})
                out.append({"type": "step", "label": "개인정보 가리기",
                            "value": ", ".join(GUARD_WORDS.get(a, a) for a in acts) if acts else "가릴 것 없음", "state": "ok"})
                out.append({"type": "answer", "text": body, "cites": cites, "guard": acts, "degraded": bool(meta.get("degraded"))})
        return out
