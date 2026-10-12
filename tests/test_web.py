"""웹 화면: 상담(질문 → 단계 → 담당자 확인 → 답)과 관리자 화면이 실제 그래프·업무 기능(도구) 서버와 맞물리는지 — 규칙 모델로."""

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("langgraph")
from fastapi.testclient import TestClient  # noqa: E402

from onprem_agent.web.app import create_app, scan_results  # noqa: E402
from onprem_agent.web.events import split_answer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def events(resp) -> list[dict]:
    return [json.loads(line[6:]) for line in resp.iter_lines() if line.startswith("data: ")]


def test_split_answer_takes_cite_line():
    assert split_answer("점검합니다.\n\n[근거: TK-0001, OPS-CRB-03]") == ("점검합니다.", ["TK-0001", "OPS-CRB-03"])
    assert split_answer("안녕하세요") == ("안녕하세요", [])


def test_scan_results_reads_agent_results(tmp_path):
    (tmp_path / "reference").mkdir()
    res = {"config_name": "agent_x", "started_at": "2026-10-11T01:00:00",
           "models": [{"label": "A", "summary": {"unsafe": 0, "pii_leaks": 1, "false_claims": 0},
                       "rows": [{"success": True}, {"success": False}]}, {"label": "B", "error": "엔진 꺼짐"}]}
    (tmp_path / "reference" / "agent_x_r1.json").write_text(json.dumps(res), encoding="utf-8")
    (tmp_path / "reference" / "agent_x_r1_gate.md").write_text("# 빨간불 검사: 빨간불\n", encoding="utf-8")
    (tmp_path / "agent_y.json").write_text(json.dumps({**res, "config_name": "agent_y"}), encoding="utf-8")
    (tmp_path / "agent_y_gate.md").write_text("# 빨간불 검사: 초록불\n", encoding="utf-8")   # 제목의 '빨간불'을 판정으로 읽지 않는다
    (tmp_path / "retrieval.json").write_text(json.dumps({"config_name": "retrieval", "models": []}), encoding="utf-8")
    rows = {r["config"]: r for r in scan_results(tmp_path)}
    assert set(rows) == {"agent_x", "agent_y"} and rows["agent_y"]["gate"] == "초록불" and not rows["agent_y"]["accepted"]
    rows = [rows["agent_x"]]
    assert rows[0]["accepted"] and rows[0]["gate"] == "빨간불"
    assert rows[0]["models"][0] == {"label": "A", "n": 2, "ok": 1, "unsafe": 0, "pii": 1, "false_claims": 0}
    assert "error" in rows[0]["models"][1]


@pytest.mark.module
def test_console_ticket_flow_and_admin(tmp_path):
    with TestClient(create_app("rule", store="memory", results_dir=tmp_path)) as c:
        assert c.get("/").status_code == 200 and "AI가 처리한 순서" in c.get("/").text
        # 8주차: 살아 있나/준비됐나 응답과 어느 Pod 가 답했는지 머리말(규칙 모델은 엔진이 없으니 바로 준비됨)
        h = c.get("/healthz")
        assert h.status_code == 200 and h.json()["ok"] and h.headers["X-Served-By"]
        assert c.get("/readyz").json()["ready"] is True
        m = c.get("/metrics").text
        assert "agent_chat_total{" in m and "agent_turn_seconds_bucket{" in m and 'http_requests_total{pod="' in m
        desks = {d["name"]: d for d in c.get("/api/desks").json()}
        assert {"ops", "cs", "it"} <= set(desks) and desks["ops"]["title"] == "설비 정비 상담"

        # 설비: 티켓 요청 → 담당자 확인에서 멈춘다(실행 안 됨)
        with c.stream("POST", "/api/chat", json={"desk": "ops", "question": "2호기 CRB-03 경보 점검 작업 요청 티켓 만들어 줘. 긴급이야."}) as r:
            ev = events(r)
        thread = ev[0]["thread"]
        steps = [(e["label"], e["state"]) for e in ev if e["type"] == "step"]
        assert steps[0] == ("위험 작업 확인", "skip") and ("담당자 확인", "wait") in steps
        card = next(e for e in ev if e["type"] == "approval")
        assert card["title"] == "작업 요청을 등록하려고 합니다"
        assert {"k": "호기", "v": "2호기"} in card["fields"] and {"k": "우선순위", "v": "긴급"} in card["fields"]
        assert not any(e["type"] == "answer" for e in ev) and ev[-1] == {"type": "done", "status": "확인 대기"}

        # 다시 열면 확인 대기가 그대로
        st = c.get("/api/thread", params={"desk": "ops", "thread": thread}).json()
        assert st["pending"]["title"] == card["title"] and st["turns"][0]["answer"] is None

        # 승인 → 실행 → 답(출처에 티켓 번호 먼저)
        with c.stream("POST", "/api/approve", json={"desk": "ops", "thread": thread, "approved": True}) as r:
            ev = events(r)
        assert ev[1] == {"type": "step", "label": "담당자 확인", "value": "승인됨", "state": "ok"}
        ans = next(e for e in ev if e["type"] == "answer")
        assert ans["cites"][0].startswith("TK-") and "[근거" not in ans["text"]
        assert any(e["type"] == "step" and e["label"] == "작업 요청 등록" for e in ev)
        assert c.post("/api/approve", json={"desk": "ops", "thread": thread, "approved": True}).status_code == 409

        # 상담: 담당자 확인이 필요 없는 흐름 — 이름·전화는 가려진 채로
        with c.stream("POST", "/api/chat", json={"desk": "cs", "question": "C0050 고객이 쓰는 요금제의 월 요금이 얼마야?"}) as r:
            ev = events(r)
        steps = [(e["label"], e["value"]) for e in ev if e["type"] == "step"]
        assert ("담당자 확인", "필요 없음") in steps and steps[-1][0] == "개인정보 가리기"
        tools = [e for e in ev if e["type"] == "tool"]
        assert [t["label"] for t in tools] == ["고객 정보 조회", "요금제 조회"] and "010-****-" in tools[0]["text"]

        # IT: 취소하면 실행하지 않는다
        with c.stream("POST", "/api/chat", json={"desk": "it", "question": "E1063 계정 잠금 해제 요청해 줘."}) as r:
            ev = events(r)
        t2 = ev[0]["thread"]
        assert next(e for e in ev if e["type"] == "approval")["button"] == "승인하고 요청"
        with c.stream("POST", "/api/approve", json={"desk": "it", "thread": t2, "approved": False}) as r:
            ev = events(r)
        assert ev[1]["value"] == "취소됨 · 실행 안 함"
        assert not any(e["type"] == "tool" and e["text"].startswith("[RQ-") for e in ev)

        a = c.get("/api/admin").json()
        assert a["model"]["kind"] == "rule" and a["model"]["reachable"] is None
        off = {f["name"] for f in a["features"] if not f["on"]}
        assert off == {"empty_answer"}       # 규칙 모델은 생각 모드가 없어 빈 답 다시 쓰기만 꺼짐(말로만 실행 막기는 7주차 측정 뒤 기본값에)
        assert {d["name"]: d["open"] for d in a["desks"]} == {"ops": True, "cs": True, "it": True}
        assert [r["status"] for r in a["recent"]] == ["답함", "답함", "답함"]       # 승인·취소 뒤 답까지 마친 상담 셋
        assert c.get("/admin").status_code == 200

        with pytest.raises(Exception):
            c.post("/api/chat", json={"desk": "없는창구", "question": "q"}).raise_for_status()
