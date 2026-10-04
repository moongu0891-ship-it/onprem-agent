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
    if kind == "qdrant":
        from .qdrant import QdrantStore
        return QdrantStore(**args)
    if kind == "milvus":
        from .milvus import MilvusStore
        return MilvusStore(**args)
    if kind == "elasticsearch":
        from .elasticsearch import ElasticsearchStore
        return ElasticsearchStore(**args)
    if kind == "weaviate":
        from .weaviate import WeaviateStore
        return WeaviateStore(**args)
    if kind == "pgvector":
        from .pgvector import PgvectorStore
        return PgvectorStore(**args)
    raise ValueError(f"알 수 없는 저장소: {kind}")
