"""하이브리드 검색: 여러 갈래의 '등수'를 RRF로 합친다.

점수 단위가 서로 달라(BM25 점수 vs 코사인 유사도) 그냥 더할 수 없으므로
점수 대신 등수를 쓴다: score = Σ 1 / (k + rank). k=60 은 Cormack 외(SIGIR 2009)의 값.
"""

from __future__ import annotations

from ..corpus import Chunk
from .base import Hit, Retriever


def rrf_fuse(rankings: list[list[Hit]], k: int = 60) -> list[Hit]:
    score: dict[str, float] = {}
    section: dict[str, str] = {}
    for hits in rankings:
        for rank, h in enumerate(hits, start=1):
            score[h.chunk_id] = score.get(h.chunk_id, 0.0) + 1.0 / (k + rank)
            section[h.chunk_id] = h.section_id
    order = sorted(score, key=lambda c: -score[c])
    return [Hit(c, section[c], score[c]) for c in order]


class HybridRetriever:
    def __init__(self, retrievers: list[Retriever], fetch_k: int = 20, rrf_k: int = 60):
        self.retrievers = retrievers
        self.fetch_k = fetch_k
        self.rrf_k = rrf_k
        self.name = "hybrid[" + "+".join(r.name for r in retrievers) + "]"

    def index(self, chunks: list[Chunk]) -> None:
        for r in self.retrievers:
            r.index(chunks)

    def search(self, query: str, k: int) -> list[Hit]:
        rankings = [r.search(query, self.fetch_k) for r in self.retrievers]
        return rrf_fuse(rankings, self.rrf_k)[:k]
