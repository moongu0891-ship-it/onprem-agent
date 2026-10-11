"""고객 상담 창구의 업무 기능(도구) 서버 (MCP, 예제). 에이전트는 이 서버가 알려 주는 업무 기능(도구)만 쓴다.

    python examples/desks/cs/server.py      # 고객 조회 · 요금제 조회 · 약관·FAQ 검색

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
import sys
from inspect import cleandoc
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # examples/desks — 두 예제 창구가 같이 쓰는 업무 DB
from shared_db import build_db  # noqa: E402

from onprem_agent.agent.tool_server import ROOT, build_search, format_hits, mask_name, mask_phone  # noqa: E402,F401
from onprem_agent.agent.tool_server import tool_examples as _ex  # noqa: E402,F401


def make_cs_server() -> FastMCP:
    mcp = FastMCP("onprem-cs")
    guard = os.environ.get("ONPREM_GUARD_DATA") == "1"
    db = build_db(ROOT, guard=guard)
    retr, by_id = build_search(["data/cs"] + (["data/guard/cs"] if guard else []))

    @mcp.tool(description=cleandoc(f"""고객 번호로 고객의 요금제, 약정, 미납 금액, 로밍 상품을 조회한다. 이름·전화번호는 가려서 돌려준다.
        customer_id: 고객 번호 {_ex("(예: C0012)", "(C 와 숫자 4자리, 질문에 나온 번호를 그대로)")}."""))
    def get_customer(customer_id: str) -> str:
        cid = customer_id.strip().upper()
        r = db.execute("SELECT * FROM customers WHERE customer_id = ?", (cid,)).fetchone()
        if not r:
            return f"고객 {cid} 없음"
        contract = f"{r['contract_months']}개월 약정(만료 {r['contract_end']})" if r["contract_months"] else "약정 없음"
        return (f"[{cid}] 고객 | 이름 {mask_name(r['name'])} | 전화 {mask_phone(r['phone'])} | 요금제 {r['plan_code']} | {contract} | "
                f"미납 {r['unpaid_amount']:,}원 | 로밍 {r['roaming_pass'] or '없음'} | 가족 회선 {r['family_lines']}개")

    @mcp.tool(description="요금제 코드로 요금제의 월 요금, 선택약정 요금, 데이터 제공량, 부가 혜택을 조회한다. plan_code: "
                          + _ex("예 PLN-5G59.", "PLN- 으로 시작하는 코드, 질문이나 고객 조회 결과에 나온 코드를 그대로."))
    def get_plan(plan_code: str) -> str:
        code = plan_code.strip().upper()
        r = db.execute("SELECT * FROM plans WHERE plan_code = ?", (code,)).fetchone()
        if not r:
            return f"요금제 {code} 없음"
        return f"[CS-{code}] {r['name']} | 월 {r['monthly_fee']:,}원 | 선택약정 시 월 {r['contract_fee']:,}원 | {r['description']}"

    @mcp.tool()
    def search_terms(query: str) -> str:
        """이용약관·자주 묻는 질문·요금제 안내에서 규정과 절차를 찾는다(위약금, 요금제 변경, 분실, 로밍, 미납 등).
        결과의 [대괄호] 안은 근거 절 번호다."""
        return format_hits(retr.search(query, 10), by_id)

    return mcp


if __name__ == "__main__":
    make_cs_server().run(transport="stdio")
