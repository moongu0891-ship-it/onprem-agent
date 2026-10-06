"""MCP 업무 기능(도구) 서버 두 개 — 에이전트는 이 서버들이 알려 주는 업무 기능(도구)만 쓴다.

    python -m onprem_agent.agent.mcp_servers ops     # 설비 정비: 매뉴얼 검색 · 작업 이력 조회 · 작업 요청 티켓
    python -m onprem_agent.agent.mcp_servers cs      # 고객 상담: 고객 조회 · 요금제 조회 · 약관·FAQ 검색

왜 MCP 인가: 업무 기능(도구)을 에이전트 코드에 붙박지 않고 표준 규약(Model Context Protocol)으로 따로 띄우면,
같은 업무 기능(도구)을 다른 에이전트·다른 회사 시스템에서도 그대로 쓰고, 업무 기능(도구) 쪽 권한·기록을 에이전트와 분리해 관리할 수 있다.

환경 변수
- ONPREM_ROOT       저장소 루트 (기본: 이 파일 기준으로 찾음)
- ONPREM_GUARD_DATA  1 이면 가드레일 평가용 자료(data/guard/: 숨은 지시가 든 작업 이력·매뉴얼 절·FAQ)를 더한다(6주차).
- ONPREM_EMBEDDER   검색 임베더 설정 JSON. 기본 {"kind":"hash"} (모델 없이 CI 에서 돈다).
                    노트북: '{"kind":"sentence-transformers","model":"BAAI/bge-m3"}'

안전 원칙
- 고객 이름·전화번호는 서버에서부터 가려서 내보낸다(모델이 원문을 볼 일이 없게).
- 상태를 바꾸는 업무 기능(도구)(create_ticket)는 에이전트 그래프가 사람의 승인을 받은 뒤에만 부른다.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .data import build_db, mask_name, mask_phone

ROOT = Path(os.environ.get("ONPREM_ROOT", Path(__file__).resolve().parents[3]))
CODE_RE = re.compile(r"^[A-Z]{3}-\d{2}$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _retriever(folders: list[str]):
    """2주차에 정한 기본 검색: 코드가 있는 질문은 BM25, 나머지는 벡터 검색."""
    from ..corpus import load_corpus
    from ..retrieval import build_retriever
    emb = json.loads(os.environ.get("ONPREM_EMBEDDER", '{"kind": "hash"}'))
    r = build_retriever({"kind": "routed", "code_route": {"kind": "bm25"},
                         "default_route": {"kind": "dense", "store": {"kind": "memory"}, "embedder": emb}})
    chunks = [c for f in folders for c in load_corpus(ROOT / f)]
    r.index(chunks)
    return r, {c.chunk_id: c for c in chunks}


def _format_hits(hits, by_id, k=3, max_chars=500) -> str:
    out, seen = [], set()
    for h in hits:
        c = by_id[h.chunk_id]
        if c.section_id in seen:
            continue
        seen.add(c.section_id)
        out.append(f"[{c.section_id}] {c.title}\n{c.text[:max_chars]}")
        if len(out) == k:
            break
    return "\n\n".join(out) if out else "검색 결과 없음"


def make_ops_server() -> FastMCP:
    mcp = FastMCP("onprem-ops")
    guard = os.environ.get("ONPREM_GUARD_DATA") == "1"
    db = build_db(ROOT, guard=guard)
    retr, by_id = _retriever(["data/ops"] + (["data/guard/ops"] if guard else []))

    @mcp.tool()
    def search_manual(query: str) -> str:
        """KX-200 설비 매뉴얼에서 경보 코드의 의미, 조치 순서, 안전 수칙, 부품 정보를 찾는다.
        '어떻게 해야 하나', '무슨 뜻인가' 처럼 절차·설명을 묻는 질문에 쓴다. 경보 코드가 있으면 query 에 그대로 넣는다.
        결과의 [대괄호] 안은 근거 절 번호다."""
        return _format_hits(retr.search(query, 10), by_id)

    @mcp.tool()
    def get_work_orders(alarm_code: str, line: int = 0, month: str = "") -> str:
        """정비 작업 이력을 조회한다. 특정 호기·경보 코드·연월에 무슨 일이 있었고 어떻게 처리했는지 묻는 질문에 쓴다.
        alarm_code: 경보 코드 (예: LVL-06). line: 호기 번호 1~6 (모르면 0). month: 연월 YYYY-MM (모르면 빈 문자열).
        결과의 [대괄호] 안은 근거가 되는 작업 번호다."""
        code = alarm_code.strip().upper()
        if not CODE_RE.match(code):
            return f"오류: 경보 코드 형식이 아니다: {alarm_code!r} (예: LVL-06)"
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


def make_cs_server() -> FastMCP:
    mcp = FastMCP("onprem-cs")
    guard = os.environ.get("ONPREM_GUARD_DATA") == "1"
    db = build_db(ROOT, guard=guard)
    retr, by_id = _retriever(["data/cs"] + (["data/guard/cs"] if guard else []))

    @mcp.tool()
    def get_customer(customer_id: str) -> str:
        """고객 번호로 고객의 요금제, 약정, 미납 금액, 로밍 상품을 조회한다. 이름·전화번호는 가려서 돌려준다.
        customer_id: 고객 번호 (예: C0012)."""
        cid = customer_id.strip().upper()
        r = db.execute("SELECT * FROM customers WHERE customer_id = ?", (cid,)).fetchone()
        if not r:
            return f"고객 {cid} 없음"
        contract = f"{r['contract_months']}개월 약정(만료 {r['contract_end']})" if r["contract_months"] else "약정 없음"
        return (f"[{cid}] 고객 | 이름 {mask_name(r['name'])} | 전화 {mask_phone(r['phone'])} | 요금제 {r['plan_code']} | {contract} | "
                f"미납 {r['unpaid_amount']:,}원 | 로밍 {r['roaming_pass'] or '없음'} | 가족 회선 {r['family_lines']}개")

    @mcp.tool()
    def get_plan(plan_code: str) -> str:
        """요금제 코드로 요금제의 월 요금, 선택약정 요금, 데이터 제공량, 부가 혜택을 조회한다. plan_code: 예 PLN-5G59."""
        code = plan_code.strip().upper()
        r = db.execute("SELECT * FROM plans WHERE plan_code = ?", (code,)).fetchone()
        if not r:
            return f"요금제 {code} 없음"
        return f"[CS-{code}] {r['name']} | 월 {r['monthly_fee']:,}원 | 선택약정 시 월 {r['contract_fee']:,}원 | {r['description']}"

    @mcp.tool()
    def search_terms(query: str) -> str:
        """이용약관·자주 묻는 질문·요금제 안내에서 규정과 절차를 찾는다(위약금, 요금제 변경, 분실, 로밍, 미납 등).
        결과의 [대괄호] 안은 근거 절 번호다."""
        return _format_hits(retr.search(query, 10), by_id)

    return mcp


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "ops"
    server = {"ops": make_ops_server, "cs": make_cs_server}[which]()
    server.run(transport="stdio")
