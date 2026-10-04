"""부하 측정에 쓸 요청 묶음. 모두 이 저장소의 실제 데이터에서 만든다.

세 가지 모양을 비교한다.
- chat       짧은 시스템 프롬프트 + 질문 하나. 앞부분 공유가 거의 없다 (일반 챗봇).
- rag        긴 에이전트 시스템 프롬프트(도구 설명 포함, 모든 요청이 같음) + 검색된 문서 3개 + 질문.
- multiturn  rag 와 같게 시작해 같은 대화에서 후속 질문 2개를 더 한다. 앞 대화가 통째로 다음 요청의 앞부분이 된다.

에이전트 요청은 대부분 rag·multiturn 모양이다. 그래서 '앞부분을 다시 계산하지 않는' 접두사 캐시가
엔진 선택의 큰 변수가 된다 — 이걸 chat 과 나란히 재서 보이려는 것.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from ..corpus import load_corpus
from ..eval.harness import load_questions
from ..retrieval import build_retriever
from .tools import TOOLS

AGENT_SYSTEM = """당신은 KX-200 생산 설비의 정비 지원 에이전트입니다.

역할
- 현장 작업자의 질문에 매뉴얼과 정비 이력을 근거로 답합니다.
- 근거 문서에 없는 내용은 추측하지 말고 '문서에서 확인되지 않습니다'라고 답합니다.
- 경보 코드는 한 글자만 달라도 다른 경보입니다. 코드를 그대로 인용합니다.
- 설비를 만지는 조치를 안내할 때는 반드시 안전 수칙(전원 차단, 잠금·표지, 잔압 해소)을 먼저 말합니다.
- 작업 요청 티켓 생성처럼 상태를 바꾸는 일은 사람의 승인을 받은 뒤에만 실행합니다.

답변 형식
- 첫 문장에 결론을 씁니다.
- 절차는 번호를 붙여 순서대로 씁니다.
- 근거로 쓴 문서의 절 번호를 마지막에 [근거: OPS-xxx] 형식으로 붙입니다.
- 개인정보(전화번호, 주소)는 답변에 쓰지 않습니다.

사용할 수 있는 도구
{tools}
"""

CHAT_SYSTEM = "질문에 한국어로 간단히 답하세요."

FOLLOW_UPS = [
    "그 조치를 하기 전에 확인해야 할 안전 사항을 다시 정리해 주세요.",
    "같은 경보가 최근에 다른 호기에서도 있었는지 확인하려면 어떻게 하나요?",
    "이 내용을 현장 작업자에게 전달할 세 줄 요약으로 만들어 주세요.",
    "필요한 부품이나 공구가 있으면 알려 주세요.",
]


def agent_system_prompt() -> str:
    return AGENT_SYSTEM.format(tools=json.dumps([t["function"] for t in TOOLS], ensure_ascii=False, indent=1))


def build_workloads(root: Path, n: int, seed: int = 7, turns: int = 3) -> dict[str, list[dict]]:
    """작업 하나 = {"system": str, "turns": [첫 질문, 후속, ...], "context": str}. 결정적으로 만든다."""
    qs = load_questions([root / "eval/questions_ops.jsonl", root / "eval/questions_ops_history.jsonl"])
    chunks = load_corpus(root / "data/ops") + load_corpus(root / "data/ops_logs")
    bm25 = build_retriever({"kind": "bm25"})
    bm25.index(chunks)
    by_id = {c.chunk_id: c for c in chunks}
    rng = random.Random(seed)
    picks = [qs[rng.randrange(len(qs))] for _ in range(n)]

    def context_for(q: str) -> str:
        hits = bm25.search(q, 3)
        return "\n\n".join(f"[{by_id[h.chunk_id].section_id}] {by_id[h.chunk_id].text}" for h in hits)

    system = agent_system_prompt()
    out = {"chat": [], "rag": [], "multiturn": []}
    for i, q in enumerate(picks):
        ctx = context_for(q["question"])
        # 사용자 메시지 맨 앞에 요청마다 다른 꼬리표를 붙인다. 같은 질문이 두 번 뽑혀도 캐시를 공짜로 얻지 않게 하려는 것.
        # 그래서 캐시가 재사용할 수 있는 건 '모든 요청이 공유하는 시스템 프롬프트'와 '같은 대화의 앞 턴'뿐이다 (실제 에이전트와 같은 조건).
        tag = f"[요청 {seed}-{i}]"
        first = f"{tag} 참고 문서:\n{ctx}\n\n질문: {q['question']}"
        out["chat"].append({"system": CHAT_SYSTEM, "turns": [f"{tag} {q['question']}"]})
        out["rag"].append({"system": system, "turns": [first]})
        follow = [FOLLOW_UPS[(i + j) % len(FOLLOW_UPS)] for j in range(turns - 1)]
        out["multiturn"].append({"system": system, "turns": [first, *follow]})
    return out
