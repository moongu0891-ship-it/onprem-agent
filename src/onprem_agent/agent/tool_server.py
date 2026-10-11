"""업무 기능(도구) 서버를 만들 때 쓰는 공통 도구 (핵심). 창구마다의 서버(examples/desks/<창구>/server.py)가 가져다 쓴다.

- 문서 검색: 2주차에 정한 기본 검색(코드가 있는 질문은 BM25, 나머지는 벡터)으로 폴더를 색인하고, 결과를 [절 번호] 와 함께 돌려준다.
- 개인정보 가리기: 이름·전화번호는 서버에서부터 가려서 내보낸다(모델이 원문을 볼 일이 없게).
- 설명 속 예시 값 켜고 끄기(6주차 ②, D30).

환경 변수
- ONPREM_ROOT          저장소 루트 (데이터 폴더의 기준)
- ONPREM_EMBEDDER      검색 임베더 설정 JSON. 기본 {"kind":"hash"} (모델 없이 CI 에서 돈다).
- ONPREM_TOOL_EXAMPLES 0 이면 업무 기능(도구) 설명에 구체 예시 값 대신 형식만 적는다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("ONPREM_ROOT", Path(__file__).resolve().parents[3]))


def tool_examples(example: str, fmt: str) -> str:
    """업무 기능(도구) 설명의 값 안내: 예시 값을 보일지(기본) 형식만 적을지(ONPREM_TOOL_EXAMPLES=0)."""
    return example if os.environ.get("ONPREM_TOOL_EXAMPLES", "1") != "0" else fmt


def build_search(folders: list[str]):
    """2주차에 정한 기본 검색: 코드가 있는 질문은 BM25, 나머지는 벡터 검색. → (검색기, 청크 id → 청크)"""
    from ..corpus import load_corpus
    from ..retrieval import build_retriever
    emb = json.loads(os.environ.get("ONPREM_EMBEDDER", '{"kind": "hash"}'))
    r = build_retriever({"kind": "routed", "code_route": {"kind": "bm25"},
                         "default_route": {"kind": "dense", "store": {"kind": "memory"}, "embedder": emb}})
    chunks = [c for f in folders for c in load_corpus(ROOT / f)]
    r.index(chunks)
    return r, {c.chunk_id: c for c in chunks}


def format_hits(hits, by_id, k=3, max_chars=500) -> str:
    """검색 결과를 절 단위로 k 개까지: '[절 번호] 제목\\n본문'. 근거 자동이 이 [절 번호] 를 쓴다."""
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


def mask_phone(phone: str) -> str:
    """010-1234-5678 → 010-****-5678 (상담원 화면에 흔히 쓰는 마스킹)."""
    parts = phone.split("-")
    return f"{parts[0]}-****-{parts[-1]}" if len(parts) == 3 else "***"


def mask_name(name: str) -> str:
    """이하은 → 이*은, 김선 → 김*."""
    if len(name) <= 1:
        return "*"
    return name[0] + "*" * (len(name) - 2) + name[-1] if len(name) > 2 else name[0] + "*"
