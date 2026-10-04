"""numpy 전수 비교. 근사 인덱스가 없어 '정답 상한'으로 쓴다.

다른 벡터DB의 Recall이 이것보다 낮으면 그 차이가 곧 근사 인덱스(HNSW 등)가 놓친 몫이다.
"""

from __future__ import annotations

import numpy as np


class MemoryStore:
    name = "memory"

    def __init__(self):
        self.ids: list[str] = []
        self.meta: list[dict] = []
        self.mat = np.zeros((0, 0), dtype=np.float32)

    def reset(self, dim: int) -> None:
        self.ids = []
        self.meta = []
        self.mat = np.zeros((0, dim), dtype=np.float32)

    def add(self, ids, vectors, metadatas) -> None:
        self.ids.extend(ids)
        self.meta.extend(metadatas or [{}] * len(ids))
        self.mat = np.vstack([self.mat, vectors.astype(np.float32)])

    def search(self, vector, k, filter=None):
        scores = self.mat @ vector.astype(np.float32)
        if filter:
            ok = np.array([all(m.get(f) == v for f, v in filter.items()) for m in self.meta])
            scores = np.where(ok, scores, -np.inf)
        top = np.argsort(-scores)[:k]
        return [(self.ids[i], float(scores[i])) for i in top if np.isfinite(scores[i])]
