"""설비 정비 창구의 업무 기능(도구) 서버 (MCP, 예제). 에이전트는 이 서버가 알려 주는 업무 기능(도구)만 쓴다.

    python examples/desks/ops/server.py      # 매뉴얼 검색 · 작업 이력 조회 · 작업 요청 티켓

왜 MCP 인가: 업무 기능(도구)을 에이전트 코드에 붙박지 않고 표준 규약(Model Context Protocol)으로 따로 띄우면,
같은 업무 기능(도구)을 다른 에이전트·다른 회사 시스템에서도 그대로 쓰고, 업무 기능(도구) 쪽 권한·기록을 에이전트와 분리해 관리할 수 있다.
핵심 코드(src/onprem_agent)는 이 파일을 모른다 — 창구 정의(desk.yaml)의 server 항목으로만 이어진다.

환경 변수
- ONPREM_GUARD_DATA  1 이면 보호 기능(가드레일) 평가용 자료(data/guard/: 숨은 지시가 든 자료)를 더한다(6주차).
- 그 밖(ONPREM_ROOT·ONPREM_EMBEDDER·ONPREM_TOOL_EXAMPLES)은 onprem_agent.agent.tool_server 를 본다.

안전 원칙
- 고객 이름·전화번호는 서버에서부터 가려서 내보낸다(모델이 원문을 볼 일이 없게).
- 상태를 바꾸는 업무 기능(도구)은 에이전트 그래프가 사람의 승인을 받은 뒤에만 부른다(창구 정의의 approval_tools).
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from inspect import cleandoc
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # examples/desks — 두 예제 창구가 같이 쓰는 업무 DB
from shared_db import build_db  # noqa: E402

from onprem_agent.agent.tool_server import ROOT, build_search, format_hits, mask_name, mask_phone  # noqa: E402,F401
from onprem_agent.agent.tool_server import tool_examples as _ex  # noqa: E402,F401

CODE_RE = re.compile(r"^[A-Z]{3}-\d{2}$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def make_ops_server() -> FastMCP:
    mcp = FastMCP("onprem-ops")
    guard = os.environ.get("ONPREM_GUARD_DATA") == "1"
    db = build_db(ROOT, guard=guard)
    retr, by_id = build_search(["data/ops"] + (["data/guard/ops"] if guard else []))

    @mcp.tool()
    def search_manual(query: str) -> str:
        """KX-200 설비 매뉴얼에서 경보 코드의 의미, 조치 순서, 안전 수칙, 부품 정보를 찾는다.
        '어떻게 해야 하나', '무슨 뜻인가' 처럼 절차·설명을 묻는 질문에 쓴다. 경보 코드가 있으면 query 에 그대로 넣는다.
        결과의 [대괄호] 안은 근거 절 번호다."""
        return format_hits(retr.search(query, 10), by_id)

    code_hint = _ex("(예: LVL-06)", "(영문 대문자 3자-숫자 2자, 질문에 나온 코드를 그대로)")

    @mcp.tool(description=cleandoc(f"""정비 작업 이력을 조회한다. 특정 호기·경보 코드·연월에 무슨 일이 있었고 어떻게 처리했는지 묻는 질문에 쓴다.
        alarm_code: 경보 코드 {code_hint}. line: 호기 번호 1~6 (모르면 0). month: 연월 YYYY-MM (모르면 빈 문자열).
        결과의 [대괄호] 안은 근거가 되는 작업 번호다."""))   # 독스트링과 같게 들여쓰기를 걷어 낸다(예시 켬 = 예전과 글자까지 같음)
    def get_work_orders(alarm_code: str, line: int = 0, month: str = "") -> str:
        code = alarm_code.strip().upper()
        if not CODE_RE.match(code):
            return f"오류: 경보 코드 형식이 아니다: {alarm_code!r} {code_hint}"
        if month and not MONTH_RE.match(month):
            return f"오류: month 는 YYYY-MM 형식이어야 한다: {month!r}"
        sql, args = "SELECT * FROM work_orders WHERE alarm_code = ?", [code]
        if line:
            sql, args = sql + " AND line = ?", args + [int(line)]
        if month:
            sql, args = sql + " AND month = ?", args + [month]
        rows = db.execute(sql + " ORDER BY date DESC", args).fetchall()
        if not rows:
            return "조건에 맞는 작업 이력이 없다."
        head = f"작업 이력 {len(rows)}건" + (" (최근 5건만 표시)" if len(rows) > 5 else "")
        body = [f"[{r['wo_id']}] {r['date']} | {r['line']}호기 | {r['alarm_code']}({r['alarm_name']}) | 점검: {r['part']} — "
                f"{r['finding']} | 조치: {r['action']} | 정지 {r['downtime_h']}시간 | 작업자 {r['worker']}" for r in rows[:5]]
        return "\n".join([head, *body])

    @mcp.tool()
    def create_ticket(line: int, alarm_code: str, summary: str, priority: str = "normal") -> str:
        """정비 작업 요청 티켓을 만든다. 사용자가 작업 요청·티켓 생성·등록을 명시적으로 요구할 때만 쓴다. 실행 전 사람의 승인이 필요하다.
        line: 호기 번호 1~6. priority: 긴급하면 high, 급하지 않으면 low, 언급이 없으면 normal."""
        code = alarm_code.strip().upper()
        if not CODE_RE.match(code) or not 1 <= int(line) <= 6:
            return f"오류: 호기(1~6)·경보 코드 형식을 확인하라: {line}, {alarm_code!r}"
        if priority not in ("low", "normal", "high"):
            return f"오류: priority 는 low·normal·high 중 하나: {priority!r}"
        n = db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] + 1
        tid = f"TK-{n:04d}"
        db.execute("INSERT INTO tickets VALUES (?,?,?,?,?,?)",
                   (tid, int(line), code, summary.strip(), priority, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        db.commit()
        return f"[{tid}] 티켓 생성됨: {line}호기 {code}, 우선순위 {priority}, 내용: {summary.strip()}"

    return mcp


if __name__ == "__main__":
    make_ops_server().run(transport="stdio")
