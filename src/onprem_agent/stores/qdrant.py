"""Qdrant 어댑터. url 을 주면 서버(Docker), 안 주면 메모리 모드(테스트용)."""

from __future__ import annotations

import uuid


def _uuid(chunk_id: str) -> str:
    # Qdrant 점 id 는 정수나 UUID 만 받는다 → 청크 id 로 결정적 UUID 를 만든다
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class QdrantStore:
    name = "qdrant"

    def __init__(self, url: str | None = None, collection: str = "chunks",
                 hnsw_m: int = 16, ef_construct: int = 100, ef_search: int = 128):
        from qdrant_client import QdrantClient
        self.client = QdrantClient(url=url, timeout=120) if url else QdrantClient(location=":memory:")
        self.collection = collection
        self.hnsw = (hnsw_m, ef_construct)
        self.ef_search = ef_search

    def reset(self, dim: int) -> None:
        from qdrant_client.models import Distance, HnswConfigDiff, VectorParams
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            self.collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            hnsw_config=HnswConfigDiff(m=self.hnsw[0], ef_construct=self.hnsw[1]),
        )
        # 필터 필드에 인덱스를 걸어야 Qdrant 가 필터를 그래프 탐색 안에서 처리한다
        from qdrant_client.models import PayloadSchemaType
        self.client.create_payload_index(self.collection, "doc_type", PayloadSchemaType.KEYWORD)

    def add(self, ids, vectors, metadatas) -> None:
        from qdrant_client.models import PointStruct
        points = [PointStruct(id=_uuid(i), vector=v.tolist(),
                              payload={"chunk_id": i, "section_id": m.get("section_id"), "doc_type": m.get("doc_type")})
                  for i, v, m in zip(ids, vectors, metadatas)]
        for s in range(0, len(points), 256):
            self.client.upsert(self.collection, points=points[s:s + 256], wait=True)

    def search(self, vector, k, filter=None):
        from qdrant_client.models import FieldCondition, Filter, MatchValue, SearchParams
        qf = (Filter(must=[FieldCondition(key=f, match=MatchValue(value=v)) for f, v in filter.items()])
              if filter else None)
        res = self.client.query_points(self.collection, query=vector.tolist(), limit=k, query_filter=qf,
                                       search_params=SearchParams(hnsw_ef=self.ef_search),
                                       with_payload=["chunk_id"])
        return [(p.payload["chunk_id"], float(p.score)) for p in res.points]
