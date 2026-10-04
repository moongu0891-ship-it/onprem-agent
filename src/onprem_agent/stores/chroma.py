"""ChromaDB 어댑터 (임베디드 모드, 서버 불필요)."""

from __future__ import annotations

import numpy as np


class ChromaStore:
    name = "chroma"

    def __init__(self, path: str | None = None, collection: str = "chunks"):
        import chromadb
        self.client = chromadb.PersistentClient(path=path) if path else chromadb.EphemeralClient()
        self.collection_name = collection
        self.col = None

    def reset(self, dim: int) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        # 정규화된 벡터 + cosine → 유사도 = 1 - distance
        self.col = self.client.create_collection(self.collection_name, metadata={"hnsw:space": "cosine"})

    def add(self, ids, vectors, metadatas) -> None:
        for i in range(0, len(ids), 1000):
            self.col.add(ids=ids[i:i + 1000], embeddings=vectors[i:i + 1000].tolist(),
                         metadatas=metadatas[i:i + 1000])

    def search(self, vector, k):
        r = self.col.query(query_embeddings=[np.asarray(vector).tolist()], n_results=k)
        return [(i, 1.0 - d) for i, d in zip(r["ids"][0], r["distances"][0])]
