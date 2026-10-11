"""고객 상담 창구의 규칙 모델 규칙 (예제) — GPU 없는 모듈 시험·기준선에 쓴다. 핵심(onprem_agent.agent.rule_model)이 불러 쓴다."""

import re

CUST = re.compile(r"\b(C\d{4})\b", re.I)
PLAN = re.compile(r"\b(PLN-[A-Z0-9]{4})\b", re.I)
CITE = re.compile(r"\[((?:OPS|CS|ERR|FAQ)-[A-Z0-9-]+|ERR-\d{3})\]")


def first_calls(q: str, call) -> list:
    calls = []
    if m := CUST.search(q):
        calls.append(call("get_customer", {"customer_id": m.group(1).upper()}))
    if m := PLAN.search(q):
        calls.append(call("get_plan", {"plan_code": m.group(1).upper()}))
    return calls or [call("search_terms", {"query": q})]


def next_calls(q: str, text: str, done: set, call) -> list:
    if "get_customer" in done and "get_plan" not in done and re.search(r"요금|얼마|월", q):
        if m := re.search(r"요금제 (PLN-[A-Z0-9]{4})", text):
            return [call("get_plan", {"plan_code": m.group(1)})]
    return []
