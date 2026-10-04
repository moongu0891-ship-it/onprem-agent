"""ChromaDB 어댑터 (임베디드 모드, 서버 불필요)."""

from __future__ import annotations

import numpy as np


class ChromaStore:
    name = "chroma"

    def __init__(self, path: str | None = None, collection: str = "chunks",
                 hnsw_m: int = 16, ef_construct: int = 100, ef_search: int = 128):
        import chromadb
        self.client = chromadb.PersistentClient(path=path) if path else chromadb.EphemeralClient()
        self.collection_name = collection
        self.col = None
        # 다른 DB 와 같은 HNSW 설정을 명시한다. 같은 설정에서도 근사 재현율이 0.94~0.95 로 다른 DB(1.00)보다 낮게 나온다
        self.hnsw = {"hnsw:M": hnsw_m, "hnsw:construction_ef": ef_construct, "hnsw:search_ef": ef_search}

    def reset(self, dim: int) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        # 정규화된 벡터 + cosine → 유사도 = 1 - distance
        self.col = self.client.create_collection(self.collection_name, metadata={"hnsw:space": "cosine", **self.hnsw})

    def add(self, ids, vectors, metadatas) -> None:
        for i in range(0, len(ids), 1000):
            self.col.add(ids=ids[i:i + 1000], embeddings=vectors[i:i + 1000].tolist(),
                         metadatas=metadatas[i:i + 1000])

    def search(self, vector, k, filter=None):
        r = self.col.query(query_embeddings=[np.asarray(vector).tolist()], n_results=k,
                           where=filter or None)
        return [(i, 1.0 - d) for i, d in zip(r["ids"][0], r["distances"][0])]
