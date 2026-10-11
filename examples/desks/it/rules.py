"""사내 IT 헬프데스크 창구의 규칙 모델 규칙 (예제) — GPU 없는 모듈 시험·기준선에 쓴다. 핵심(onprem_agent.agent.rule_model)이 불러 쓴다."""

import re

EMP = re.compile(r"\b(E\d{4})\b", re.I)
ASSET = re.compile(r"\b((?:NB|PJ|MN)-\d{4})\b", re.I)
CITE = re.compile(r"\[((?:IT|ITFAQ|RQ)-[A-Z0-9-]+|E\d{4}|(?:NB|PJ|MN)-\d{4})\]")
ITEM = re.compile(r"(프로젝터|보조 모니터|모니터|태블릿)")
DAYS = re.compile(r"(\d+)\s*일")
GREETING = "안녕하세요. 계정·비밀번호·VPN·장비 대여·IT 규정에 대해 물어보세요."


def first_calls(q: str, call) -> list:
    emp, asset = EMP.search(q), ASSET.search(q)
    if emp and re.search(r"잠금 해제|잠금 풀|풀어", q):
        return [call("request_unlock", {"employee_id": emp.group(1).upper(), "reason": q[:60]})]
    if emp and re.search(r"대여|빌리", q) and (item := ITEM.search(q)):
        days = DAYS.search(q)
        name = "보조 모니터" if item.group(1) == "모니터" else item.group(1)
        return [call("request_loan", {"employee_id": emp.group(1).upper(), "item": name, "days": int(days.group(1)) if days else 7})]
    if emp:
        return [call("get_employee", {"employee_id": emp.group(1).upper()})]
    if asset:
        return [call("get_asset", {"asset_tag": asset.group(1).upper()})]
    return [call("search_policy", {"query": q})]


def next_calls(q: str, text: str, done: set, call) -> list:
    if "get_employee" in done and "get_asset" not in done and re.search(r"노트북|보증", q):
        if m := re.search(r"지급 노트북 (NB-\d{4})", text):
            return [call("get_asset", {"asset_tag": m.group(1)})]
    return []
