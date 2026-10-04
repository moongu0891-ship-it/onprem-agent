"""하이브리드 검색: 여러 갈래의 '등수'를 RRF로 합친다.

점수 단위가 서로 달라(BM25 점수 vs 코사인 유사도) 그냥 더할 수 없으므로
점수 대신 등수를 쓴다: score = Σ w_i / (k + rank_i). k=60 은 Cormack 외(SIGIR 2009)의 값.

1주차 측정 결과, 같은 무게(w=1)로 합치면 '어려운 질문'에서 BM25 의 오답이 섞여
벡터 단독보다 나빠졌다. 그래서 두 가지 대안을 둔다.
- weights      : 갈래별 무게 (예: BM25 0.3, 벡터 1.0)
- RoutedRetriever : 질문에 코드(CRB-03, PLN-5G55 …)가 있을 때만 하이브리드, 아니면 벡터 단독
"""

from __future__ import annotations

from ..corpus import Chunk
from ..tokenize_ko import CODE_RE
from .base import Hit, Retriever


def rrf_fuse(rankings: list[list[Hit]], k: int = 60, weights: list[float] | None = None) -> list[Hit]:
    weights = weights or [1.0] * len(rankings)
    score: dict[str, float] = {}
    section: dict[str, str] = {}
    for w, hits in zip(weights, rankings):
        for rank, h in enumerate(hits, start=1):
            score[h.chunk_id] = score.get(h.chunk_id, 0.0) + w / (k + rank)
            section[h.chunk_id] = h.section_id
    order = sorted(score, key=lambda c: -score[c])
    return [Hit(c, section[c], score[c]) for c in order]


class HybridRetriever:
    def __init__(self, retrievers: list[Retriever], fetch_k: int = 20, rrf_k: int = 60,
                 weights: list[float] | None = None):
        if weights and len(weights) != len(retrievers):
            raise ValueError("weights 길이가 갈래 수와 달라요")
        self.retrievers = retrievers
        self.fetch_k = fetch_k
        self.rrf_k = rrf_k
        self.weights = weights
        w = f"w={weights}" if weights else ""
        self.name = "hybrid[" + "+".join(r.name for r in retrievers) + "]" + w

    def index(self, chunks: list[Chunk]) -> None:
        for r in self.retrievers:
            r.index(chunks)

    def search(self, query: str, k: int) -> list[Hit]:
        rankings = [r.search(query, self.fetch_k) for r in self.retrievers]
        return rrf_fuse(rankings, self.rrf_k, self.weights)[:k]


class RoutedRetriever:
    """질문에 코드형 토큰이 있으면 code_route, 없으면 default_route 로 보낸다."""

    def __init__(self, code_route: Retriever, default_route: Retriever):
        self.code_route = code_route
        self.default_route = default_route
        self.name = f"routed[code→{code_route.name} | else→{default_route.name}]"

    def index(self, chunks: list[Chunk]) -> None:
        self.code_route.index(chunks)
        self.default_route.index(chunks)

    def search(self, query: str, k: int) -> list[Hit]:
        route = self.code_route if CODE_RE.search(query) else self.default_route
        return route.search(query, k)
