"""서빙 측정기를 가짜 OpenAI 호환 서버로 검사한다 (GPU·Docker 없이 CI 에서 돈다)."""

import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from onprem_agent.serving.bench import run_level, summarize
from onprem_agent.serving.toolcheck import load_cases, run_toolcheck, score_case
from onprem_agent.serving.workloads import build_workloads

ROOT = Path(__file__).resolve().parents[1]
pytest.importorskip("httpx")


class FakeEngine(BaseHTTPRequestHandler):
    """토큰 하나에 2ms. 시스템 프롬프트 길이를 '캐시 재사용'으로 돌려준다."""
    seen_prefixes: set = set()

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"data":[{"id":"fake"}]}')

    def do_POST(self):
        if not self.path.startswith("/v1/"):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = sum(len(m["content"]) for m in body["messages"])
        sys_len = len(body["messages"][0]["content"])
        cached = sys_len if body["messages"][0]["content"] in FakeEngine.seen_prefixes else 0
        FakeEngine.seen_prefixes.add(body["messages"][0]["content"])
        if body.get("tools"):
            q = body["messages"][-1]["content"]
            if "이력" in q:
                msg = {"role": "assistant", "content": None, "tool_calls": [{"type": "function", "function": {
                    "name": "get_work_orders", "arguments": json.dumps({"line": 1, "alarm_code": "lvl-06", "month": "2025-07"})}}]}
            elif "안녕" in q:
                msg = {"role": "assistant", "content": "안녕하세요"}
            else:
                msg = {"role": "assistant", "content": None, "tool_calls": [{"type": "function", "function": {
                    "name": "search_manual", "arguments": "{not json"}}]}
            out = json.dumps({"choices": [{"message": msg}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        n = body["max_tokens"]
        for i in range(n):
            time.sleep(0.002)
            self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': '가'}}]})}\n\n".encode())
            self.wfile.flush()
        usage = {"completion_tokens": n, "prompt_tokens": prompt, "prompt_tokens_details": {"cached_tokens": cached}}
        self.wfile.write(f"data: {json.dumps({'choices': [], 'usage': usage})}\n\ndata: [DONE]\n\n".encode())


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeEngine)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


def test_workloads_share_system_prompt_but_not_user_turns():
    wl = build_workloads(ROOT, 6, seed=1)
    assert len({j["system"] for j in wl["rag"]}) == 1          # 모든 요청이 같은 시스템 프롬프트
    assert len({j["turns"][0] for j in wl["rag"]}) == 6         # 사용자 메시지는 모두 다름(꼬리표)
    assert all(len(j["turns"]) == 3 for j in wl["multiturn"])
    assert "get_work_orders" in wl["rag"][0]["system"]          # 도구 설명이 시스템 프롬프트에 들어 있음


def test_bench_measures_ttft_tpot_and_cache(server):
    wl = build_workloads(ROOT, 4, seed=2)
    results, dur = asyncio.run(run_level(server, "fake", wl["multiturn"], 2, 16))
    assert len(results) == 12 and all(r.ok for r in results)   # 대화 4개 × 3턴
    s = summarize(results, dur, {"ttft_ms": 1000, "tpot_ms": 50})
    assert s["errors"] == 0 and s["mean_out_tokens"] == 16
    assert s["ttft_ms"]["p50"] > 0 and 1.0 <= s["tpot_ms"]["p50"] < 50
    assert s["slo_attainment"] == 1.0
    assert 0 < s["cache_hit_ratio"] < 1                          # 시스템 프롬프트만큼 재사용
    assert s["token_source"] == ["usage"]


def test_bench_counts_failures(server):
    wl = build_workloads(ROOT, 2, seed=3)
    results, dur = asyncio.run(run_level(server.replace("/v1", "/nope"), "fake", wl["chat"], 1, 4))
    s = summarize(results, dur, {"ttft_ms": 1000, "tpot_ms": 50})
    assert s["errors"] == 2 and s["goodput_req_per_s"] == 0


def test_toolcheck_scoring(server):
    cases = [c for c in load_cases(ROOT / "eval/toolcalls.jsonl") if c["id"] in ("tc01", "tc06", "tc19", "tc15")]
    t = asyncio.run(run_toolcheck(server, "fake", cases))
    by = {m["id"]: m for m in t["misses"]}
    assert "tc06" not in by and "tc19" not in by       # 이력 질문: 대소문자 무시하고 인자 일치 / 인사: 안 부름이 정답
    assert by["tc01"]["parse_error"]                    # 깨진 JSON 인자
    assert by["tc15"]["got"] == "search_manual"         # 엉뚱한 도구
    assert t["parse_errors"] == 2 and t["args_accuracy"] == 0.5


def test_score_case_wildcard_and_numbers():
    case = {"id": "x", "tool": "create_ticket", "args": {"line": 1, "priority": "high", "summary": "*"}}
    msg = {"tool_calls": [{"function": {"name": "create_ticket",
                                        "arguments": '{"line": "1", "priority": "High", "summary": "점검"}'}}]}
    assert score_case(case, msg)["args_ok"]
    msg["tool_calls"][0]["function"]["arguments"] = '{"line": 1, "priority": "high", "summary": ""}'
    assert not score_case(case, msg)["args_ok"]
