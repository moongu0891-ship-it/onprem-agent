from __future__ import annotations

from typing import Protocol

import numpy as np


class VectorStore(Protocol):
    """모든 벡터DB 어댑터가 지키는 최소 계약.

    - reset(dim): 컬렉션을 비우고 차원을 정한다 (벤치마크마다 같은 조건에서 시작하려고)
    - add(ids, vectors, metadatas): 일괄 색인
    - search(vector, k): (id, 유사도) 를 높은 순으로 k개
    """

    name: str

    def reset(self, dim: int) -> None: ...

    def add(self, ids: list[str], vectors: np.ndarray, metadatas: list[dict]) -> None: ...

    def search(self, vector: np.ndarray, k: int) -> list[tuple[str, float]]: ...


def make_store(spec: dict) -> VectorStore:
    kind = spec.get("kind", "memory")
    args = {k: v for k, v in spec.items() if k != "kind"}
    if kind == "memory":
        from .memory import MemoryStore
        return MemoryStore(**args)
    if kind == "chroma":
        from .chroma import ChromaStore
        return ChromaStore(**args)
    raise ValueError(f"아직 없는 저장소: {kind} (2~3주차에 추가 예정)")
