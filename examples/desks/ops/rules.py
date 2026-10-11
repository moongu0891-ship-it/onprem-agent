"""설비 정비 창구의 규칙 모델 규칙 (예제) — GPU 없는 모듈 시험·기준선에 쓴다. 핵심(onprem_agent.agent.rule_model)이 불러 쓴다.

first_calls(q, call)              첫 질문에서 부를 업무 기능(도구) 목록
next_calls(q, text, done, call)   업무 기능(도구) 결과(text)를 보고 한 단계 더 갈지
CITE                              결과에서 근거로 옮겨 적을 [번호]
"""

import re

ALARM = re.compile(r"\b([A-Z]{3}-\d{2})\b")
LINE = re.compile(r"(\d)\s*호기")
MONTH = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월")
CITE = re.compile(r"\[((?:OPS|CS|ERR|FAQ)-[A-Z0-9-]+|ERR-\d{3})\]")
TICKET = re.compile(r"티켓|작업 요청|요청 등록|요청 올려|등록해")


def priority(q: str) -> str:
    if re.search(r"급하지 않|천천히|여유", q):
        return "low"
    if re.search(r"긴급|빨리|급해|최대한 빨리|즉시", q):
        return "high"
    return "normal"


def _ticket(call, q, alarm, line):
    return call("create_ticket", {"line": int(line.group(1)), "alarm_code": alarm.group(1),
                                  "summary": f"{line.group(1)}호기 {alarm.group(1)} 경보 점검 요청", "priority": priority(q)})


def first_calls(q: str, call) -> list:
    alarm = ALARM.search(q)
    wants_ticket = TICKET.search(q)
    line = LINE.search(q)
    if alarm and re.search(r"이력|기록|내역|했었|처리한|건은", q) and not wants_ticket:
        args = {"alarm_code": alarm.group(1)}
        if line:
            args["line"] = int(line.group(1))
        if m := MONTH.search(q):
            args["month"] = f"{m.group(1)}-{int(m.group(2)):02d}"
        return [call("get_work_orders", args)]
    if wants_ticket and alarm and line:
        if re.search(r"조치|방법|순서|알려", q):       # 조치 안내 + 티켓: 검색 먼저, 티켓은 다음 단계에서
            return [call("search_manual", {"query": alarm.group(1) + " 조치 순서"})]
        return [_ticket(call, q, alarm, line)]
    return [call("search_manual", {"query": q})]


def next_calls(q: str, text: str, done: set, call) -> list:
    if "search_manual" in done and "create_ticket" not in done and TICKET.search(q):
        alarm, line = ALARM.search(q), LINE.search(q)
        if alarm and line:
            return [_ticket(call, q, alarm, line)]
    return []
