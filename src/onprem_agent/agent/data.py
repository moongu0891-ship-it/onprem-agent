"""에이전트 업무 기능(도구)이 조회하는 업무 DB (SQLite).

저장소의 가상 데이터 파일에서 결정적으로 만든다. 실제 회사라면 MES·CRM 같은 기존 시스템의 DB 자리다.
- work_orders : 정비 작업 이력 2,400건 (data/ops_logs/*.md 를 구조화)
- customers   : 가상 고객 60명 (data/cs/customers.csv)
- plans       : 요금제 8종 (data/cs/plans.md 를 구조화)
- tickets     : 에이전트가 만든 정비 작업 요청 (승인을 거친 것만 들어온다)

검색(매뉴얼·약관)은 문서 검색으로, 정확한 값(이력·고객·요금)은 SQL 로 — 질문 종류에 맞는 업무 기능(도구)을 쓰게 하는 것이 2주차의 교훈
(날짜로 찾는 이력 질문은 문서 검색이 약했다)을 에이전트 설계로 옮긴 것이다.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path

WO_RE = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2}) KX-200 (?P<line>\d+)호기에서 (?P<code>[A-Z]{3}-\d{2})\((?P<name>[^)]+)\) 경보 발생\. "
    r"점검 결과 (?P<part>.+?) — (?P<finding>.+?)\. 조치: (?P<action>.+?)\. 정지 시간 (?P<hours>[\d.]+)시간\. 작업자 (?P<worker>\S+?)\.")
PLAN_HEAD_RE = re.compile(r"^## 요금제 (?P<name>.+) \((?P<code>PLN-[A-Z0-9]+)\)$")


def _won(text: str, pattern: str) -> int | None:
    m = re.search(pattern, text)
    return int(m.group(1).replace(",", "")) if m else None


def build_db(root: Path, path: str = ":memory:", guard: bool = False) -> sqlite3.Connection:
    """guard=True 면 보호 기능(가드레일) 평가용 작업 이력(data/guard/ops_logs, 숨은 지시 포함)도 넣는다."""
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript("""
        DROP TABLE IF EXISTS work_orders; DROP TABLE IF EXISTS customers; DROP TABLE IF EXISTS plans; DROP TABLE IF EXISTS tickets;
        CREATE TABLE work_orders (wo_id TEXT PRIMARY KEY, date TEXT, month TEXT, line INTEGER, alarm_code TEXT, alarm_name TEXT,
                                  part TEXT, finding TEXT, action TEXT, downtime_h REAL, worker TEXT);
        CREATE TABLE customers (customer_id TEXT PRIMARY KEY, name TEXT, phone TEXT, plan_code TEXT, contract_months INTEGER,
                                contract_end TEXT, unpaid_amount INTEGER, roaming_pass TEXT, family_lines INTEGER);
        CREATE TABLE plans (plan_code TEXT PRIMARY KEY, name TEXT, monthly_fee INTEGER, contract_fee INTEGER, description TEXT);
        CREATE TABLE tickets (ticket_id TEXT PRIMARY KEY, line INTEGER, alarm_code TEXT, summary TEXT, priority TEXT, created_at TEXT);
        CREATE INDEX wo_key ON work_orders(alarm_code, line, month);
    """)
    log_dirs = [root / "data/ops_logs"] + ([root / "data/guard/ops_logs"] if guard else [])
    for f in sorted(x for d in log_dirs for x in d.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        for block in text.split("\n## ")[1:]:
            wo_id = re.search(r"<!-- id: (WO-\d+) -->", block).group(1)
            m = WO_RE.search(block)
            if not m:
                raise ValueError(f"작업 이력 형식이 다름: {wo_id}")
            g = m.groupdict()
            con.execute("INSERT INTO work_orders VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (wo_id, g["date"], g["date"][:7], int(g["line"]), g["code"], g["name"], g["part"], g["finding"],
                         g["action"], float(g["hours"]), g["worker"]))
    with open(root / "data/cs/customers.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            con.execute("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?)",
                        (r["customer_id"], r["name"], r["phone"], r["plan_code"], int(r["contract_months"]),
                         r["contract_end"], int(r["unpaid_amount"]), r["roaming_pass"], int(r["family_lines"])))
    name = None
    for line in (root / "data/cs/plans.md").read_text(encoding="utf-8").splitlines():
        m = PLAN_HEAD_RE.match(line)
        if m:
            name, code = m.group("name"), m.group("code")
        elif name and line and not line.startswith("<!--"):
            con.execute("INSERT INTO plans VALUES (?,?,?,?,?)",
                        (code, name, _won(line, r"월 ([\d,]+)원이다"), _won(line, r"선택약정 시 월 ([\d,]+)원"), line))
            name = None
    con.commit()
    return con


def mask_phone(phone: str) -> str:
    """010-1234-5678 → 010-****-5678 (상담원 화면에 흔히 쓰는 마스킹)."""
    parts = phone.split("-")
    return f"{parts[0]}-****-{parts[-1]}" if len(parts) == 3 else "***"


def mask_name(name: str) -> str:
    """이하은 → 이*은, 김선 → 김*."""
    if len(name) <= 1:
        return "*"
    return name[0] + "*" * (len(name) - 2) + name[-1] if len(name) > 2 else name[0] + "*"
