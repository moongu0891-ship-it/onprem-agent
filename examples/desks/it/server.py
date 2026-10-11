"""사내 IT 헬프데스크 창구의 업무 기능(도구) 서버 (MCP, 예제). 7주차 ④ — 핵심 코드를 고치지 않고 창구 폴더 하나로 붙인 세 번째 창구.

    python examples/desks/it/server.py      # IT 규정 검색 · 직원 계정 조회 · 자산 조회 · 계정 잠금 해제 요청 · 장비 대여 요청

데이터는 이 폴더의 data/ (make_data.py 로 만든 가상 데이터). 실제 회사라면 사내 규정 문서·인사/계정 시스템·자산 관리 시스템 자리다.
안전 원칙은 다른 창구와 같다: 이름·휴대폰은 서버에서부터 가리고, 상태를 바꾸는 요청은 그래프가 사람의 승인을 받은 뒤에만 부른다(desk.yaml 의 approval_tools).
"""

from __future__ import annotations

import csv
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from onprem_agent.agent.tool_server import build_search, format_hits, mask_name, mask_phone

HERE = Path(__file__).resolve().parent
EMP_RE = re.compile(r"^E\d{4}$")
ASSET_RE = re.compile(r"^(NB|PJ|MN)-\d{4}$")
LOAN_ITEMS = ("프로젝터", "보조 모니터", "태블릿")


def build_db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE employees (employee_id TEXT PRIMARY KEY, name TEXT, dept TEXT, phone TEXT, status TEXT, lock_reason TEXT,
                                pwd_expiry TEXT, laptop TEXT);
        CREATE TABLE assets (asset_tag TEXT PRIMARY KEY, kind TEXT, model TEXT, assigned_to TEXT, warranty_end TEXT, status TEXT);
        CREATE TABLE requests (request_id TEXT PRIMARY KEY, kind TEXT, employee_id TEXT, detail TEXT, created_at TEXT);""")
    for table in ("employees", "assets"):
        with open(HERE / "data" / f"{table}.csv", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        con.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * len(rows[0]))})", [tuple(r.values()) for r in rows])
    return con


def make_it_server() -> FastMCP:
    mcp = FastMCP("onprem-it")
    db = build_db()
    retr, by_id = build_search([str(HERE / "data")])        # 절대 경로 — 저장소 밖 창구 폴더(ONPREM_DESKS)여도 된다

    def new_request(kind: str, emp: str, detail: str) -> str:
        n = db.execute("SELECT COUNT(*) FROM requests").fetchone()[0] + 1
        rid = f"RQ-{n:04d}"
        db.execute("INSERT INTO requests VALUES (?,?,?,?,?)", (rid, kind, emp, detail, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        db.commit()
        return rid

    @mcp.tool()
    def search_policy(query: str) -> str:
        """사내 IT 규정과 자주 묻는 질문에서 절차·규칙·오류 코드의 뜻을 찾는다(비밀번호, VPN, 장비 대여, 소프트웨어 설치, 보안 사고, 메일).
        오류 코드가 있으면 query 에 그대로 넣는다. 결과의 [대괄호] 안은 근거 절 번호다."""
        return format_hits(retr.search(query, 10), by_id)

    @mcp.tool()
    def get_employee(employee_id: str) -> str:
        """사번으로 직원 계정 상태(정상·잠김과 그 이유), 비밀번호 만료일, 지급 노트북 자산 번호를 조회한다. 이름·휴대폰은 가려서 돌려준다.
        employee_id: 사번(E 와 숫자 4자리, 질문에 나온 번호를 그대로)."""
        eid = employee_id.strip().upper()
        if not EMP_RE.match(eid):
            return f"오류: 사번 형식이 아니다(E 와 숫자 4자리): {employee_id!r}"
        r = db.execute("SELECT * FROM employees WHERE employee_id = ?", (eid,)).fetchone()
        if not r:
            return f"직원 {eid} 없음"
        lock = f"잠김({r['lock_reason']})" if r["status"] == "잠김" else "정상"
        return (f"[{eid}] 직원 | 이름 {mask_name(r['name'])} | {r['dept']} | 휴대폰 {mask_phone(r['phone'])} | 계정 {lock} | "
                f"비밀번호 만료 {r['pwd_expiry']} | 지급 노트북 {r['laptop']}")

    @mcp.tool()
    def get_asset(asset_tag: str) -> str:
        """자산 번호로 IT 장비(노트북 NB-, 프로젝터 PJ-, 보조 모니터 MN-)의 모델, 사용자 사번, 보증 만료일, 상태를 조회한다.
        asset_tag: 자산 번호(질문이나 직원 조회 결과에 나온 번호를 그대로)."""
        tag = asset_tag.strip().upper()
        if not ASSET_RE.match(tag):
            return f"오류: 자산 번호 형식이 아니다(NB-·PJ-·MN- 와 숫자 4자리): {asset_tag!r}"
        r = db.execute("SELECT * FROM assets WHERE asset_tag = ?", (tag,)).fetchone()
        if not r:
            return f"자산 {tag} 없음"
        return (f"[{tag}] {r['kind']} {r['model']} | 사용자 {r['assigned_to'] or '없음'} | 보증 만료 {r['warranty_end']} | 상태 {r['status']}")

    @mcp.tool()
    def request_unlock(employee_id: str, reason: str) -> str:
        """잠긴 사내 계정의 잠금 해제를 요청한다. 사용자가 잠금 해제를 명시적으로 요구할 때만 쓴다. 실행 전 사람의 승인이 필요하다.
        employee_id: 사번. reason: 잠긴 이유와 본인 확인 여부를 한 줄로."""
        eid = employee_id.strip().upper()
        r = db.execute("SELECT status FROM employees WHERE employee_id = ?", (eid,)).fetchone() if EMP_RE.match(eid) else None
        if not r:
            return f"오류: 직원 {employee_id!r} 없음"
        if r["status"] != "잠김":
            return f"오류: {eid} 계정은 잠겨 있지 않다(상태 {r['status']})."
        rid = new_request("잠금 해제", eid, reason.strip())
        return f"[{rid}] 계정 잠금 해제 요청 접수됨: {eid}, 사유: {reason.strip()}"

    @mcp.tool()
    def request_loan(employee_id: str, item: str, days: int) -> str:
        """장비 대여 요청을 접수한다(프로젝터·보조 모니터·태블릿, 최대 14일). 사용자가 대여 요청을 명시적으로 요구할 때만 쓴다. 실행 전 사람의 승인이 필요하다.
        employee_id: 빌리는 직원의 사번. item: 프로젝터 · 보조 모니터 · 태블릿 중 하나. days: 대여 일수 1~14."""
        eid = employee_id.strip().upper()
        if not EMP_RE.match(eid) or not db.execute("SELECT 1 FROM employees WHERE employee_id = ?", (eid,)).fetchone():
            return f"오류: 직원 {employee_id!r} 없음"
        if item.strip() not in LOAN_ITEMS:
            return f"오류: item 은 {', '.join(LOAN_ITEMS)} 중 하나: {item!r}"
        if not 1 <= int(days) <= 14:
            return f"오류: 대여 기간은 1~14일: {days!r}"
        rid = new_request("장비 대여", eid, f"{item.strip()} {int(days)}일")
        return f"[{rid}] 장비 대여 요청 접수됨: {eid}, {item.strip()} {int(days)}일. 접수 다음 근무일 오전 10시부터 3층 IT 지원실에서 받는다."

    return mcp


if __name__ == "__main__":
    make_it_server().run(transport="stdio")
