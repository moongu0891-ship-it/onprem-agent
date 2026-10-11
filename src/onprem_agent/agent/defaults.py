"""지금 기본값 (핵심) — 측정으로 고른 설정을 한곳에. 대화 프로그램(scripts/agent_chat.py)과 웹 화면(onprem_agent.web)이 같은 에이전트를 만든다.

README 의 '지금 기본값' 표와 agent/README 6.16 의 결정이 이 파일이다. 새 기능은 설정으로 켜고 끄며 기본은 끔이고,
측정으로 좋다고 확인된 것만 여기에 넣는다(docs/재는_방법.md 2-3).
"""

from __future__ import annotations

from .desk import load_desk
from .graph import build_graph
from .prompts import system_prompt
from .runner import make_model

# 모델 — 이름 하나로 고른다
MODELS = {
    "rule": {"kind": "rule"},
    "sglang": {"kind": "openai", "base_url": "http://localhost:30000/v1", "model": "qwen3-1.7b"},
    # 4·5주차 측정으로 고른 기본값: Qwen3-4B(FP8) + 생각 모드
    "sglang-4b": {"kind": "openai", "base_url": "http://localhost:30000/v1", "model": "qwen3-4b",
                  "thinking": True, "max_tokens": 2048, "timeout": 300},
    "vllm": {"kind": "openai", "base_url": "http://localhost:8000/v1", "model": "qwen3-1.7b"},
    # 5주차 결정: 게이트웨이 이름 agent-llm-4b (Qwen3-4B(FP8) + 생각 모드, 1순위 장애 시 CPU 대체 → 답에 지연 안내)
    "gateway": {"kind": "openai", "base_url": "http://localhost:4000/v1", "model": "agent-llm-4b", "api_key": "sk-local-dev",
                "thinking": True, "max_tokens": 2048, "timeout": 900, "response_headers": True},
}

PROMPT_RULES = ("scope",)                      # 6주차 ⑤·⑦: 창구 범위 규칙
GRAPH = {
    "require_tool": True, "nudge": "search",   # 4주차 되돌림 → 6주차 ④ 검색 되돌림
    "auto_cite": True,                         # 4주차 근거 자동
    "safety_search": True,                     # 5주차 안전 질문 검색
    "recover_text_calls": True,                # 6주차 ⑦ 글 호출 살리기(D37)
    "strip_injection": True,                   # 6주차 지시문 제거
    "answer_guard": True,                      # 6주차 답 검사
    "claim_check": "force",                    # 7주차 말로만 실행 막기(선택 강제) — D42·D43, 바탕과 두 번씩 재서 채택
}
EMPTY_ANSWER = True                            # 6주차 빈 답 다시 쓰기(D38) — 생각 모드를 켠 모델에만

# 관리자 화면에 보이는 이름: (설정 이름, 사람이 읽는 이름, 하는 일, 묶음)
FEATURES = [
    ("nudge", "검색 되돌림", "찾아보지 않고 답하려 하면 되돌려 먼저 찾게 한다", "안전 기능"),
    ("auto_cite", "근거 자동", "실제로 찾아본 자료의 번호만 답에 붙인다", "안전 기능"),
    ("safety_search", "안전 질문 검색", "다칠 수 있는 작업 질문은 매뉴얼부터 찾는다", "안전 기능"),
    ("recover_text_calls", "글 호출 살리기", "AI 가 업무 요청을 글로 써 버려도 실제 요청으로 살린다", "안전 기능"),
    ("empty_answer", "빈 답 다시 쓰기", "생각이 길어 답이 비면 생각 없이 다시 쓴다", "안전 기능"),
    ("claim_check", "말로만 실행 막기", "실행하지 않은 일을 했다고 답하면 요청 기능/실행 안 함 중 하나를 고르게 한다(글로 답할 틈 없음)", "안전 기능"),
    ("strip_injection", "지시문 제거", "자료 속에 숨은 'AI 는 ~하라' 문장을 지운다", "보호 기능(가드레일)"),
    ("answer_guard", "답 검사", "보내기 전에 전화번호·주민등록번호를 가리고 내부 지시문 유출을 막는다", "보호 기능(가드레일)"),
    ("scope", "창구 범위 규칙", "다른 창구의 일은 맞는 창구로 안내한다", "보호 기능(가드레일)"),
]


def model_spec(model_key: str) -> dict:
    """모델 설정. 환경 변수로 주소와 키를 바꿔 끼운다(8주차: 클러스터 안에서는 서비스 이름으로 붙고, 키는 Secret 에서 온다).
    ONPREM_MODEL_URL=http://sglang.lab:30000/v1 · ONPREM_MODEL_KEY=<게이트웨이 키>"""
    import os
    spec = dict(MODELS[model_key])
    if spec.get("kind") == "openai":
        if os.environ.get("ONPREM_MODEL_URL"):
            spec["base_url"] = os.environ["ONPREM_MODEL_URL"]
        if os.environ.get("ONPREM_MODEL_KEY"):
            spec["api_key"] = os.environ["ONPREM_MODEL_KEY"]
    return spec


def build_default_app(desk_name: str, model_key: str, tools, checkpointer=None):
    """지금 기본값으로 창구 하나의 에이전트를 만든다."""
    spec = model_spec(model_key)
    desk = load_desk(desk_name)
    return build_graph(
        make_model(spec, desk_name), tools, system_prompt(desk, PROMPT_RULES), checkpointer=checkpointer,
        empty_answer_model=(make_model({**spec, "thinking": False, "max_tokens": 1024}, desk_name)
                            if EMPTY_ANSWER and spec.get("thinking") else None),
        degraded_notice=model_key == "gateway",
        **GRAPH, **desk.graph_kwargs())
