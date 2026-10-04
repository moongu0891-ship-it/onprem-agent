"""리랭커: 넉넉히 꺼낸 후보를 질문과 '같이 읽어' 다시 줄 세운다.

임베딩 검색은 질문과 문서를 따로 숫자로 바꿔 비교하지만, 크로스 인코더는 둘을 한 입력으로 읽는다.
더 정확하지만 후보마다 모델을 한 번씩 돌려야 해서 느리다 → 후보 수(fetch_k)가 정확도·지연의 손잡이다.
"""

from __future__ import annotations

import time
from typing import Callable

from ..corpus import Chunk
from .base import Hit, Retriever

Scorer = Callable[[str, list[str]], list[float]]


def cross_encoder_scorer(model: str = "BAAI/bge-reranker-v2-m3", device: str | None = None,
                         batch_size: int = 16, max_length: int = 512) -> Scorer:
    from sentence_transformers import CrossEncoder
    ce = CrossEncoder(model, device=device, max_length=max_length)

    def score(query: str, texts: list[str]) -> list[float]:
        return [float(s) for s in ce.predict([(query, t) for t in texts], batch_size=batch_size)]
    return score


class RerankRetriever:
    def __init__(self, inner: Retriever, scorer: Scorer, fetch_k: int = 30, scorer_name: str = "reranker"):
        self.inner = inner
        self.scorer = scorer
        self.fetch_k = fetch_k
        self.name = f"rerank[{scorer_name}·top{fetch_k}]({inner.name})"
        self.rerank_ms: list[float] = []

    def index(self, chunks: list[Chunk]) -> None:
        self.inner.index(chunks)
        self.text = {c.chunk_id: c.text for c in chunks}
        self.rerank_ms = []

    def search(self, query: str, k: int, filter: dict | None = None) -> list[Hit]:
        cands = self.inner.search(query, max(self.fetch_k, k), filter)
        t = time.perf_counter()
        scores = self.scorer(query, [self.text[h.chunk_id] for h in cands])
        self.rerank_ms.append((time.perf_counter() - t) * 1000)
        order = sorted(range(len(cands)), key=lambda i: -scores[i])
        return [Hit(cands[i].chunk_id, cands[i].section_id, scores[i]) for i in order][:k]
