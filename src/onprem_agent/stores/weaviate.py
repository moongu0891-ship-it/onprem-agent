"""Weaviate 어댑터 (v4 클라이언트, 벡터는 직접 넣는 self_provided 방식)."""

from __future__ import annotations

import uuid


class WeaviateStore:
    name = "weaviate"

    def __init__(self, host: str = "localhost", port: int = 8080, grpc_port: int = 50051,
                 collection: str = "Chunks", ef_search: int = 128):
        import weaviate
        self.client = weaviate.connect_to_local(host=host, port=port, grpc_port=grpc_port)
        self.collection_name = collection
        self.ef_search = ef_search

    def reset(self, dim: int) -> None:
        from weaviate.classes.config import Configure, DataType, Property, VectorDistances
        if self.client.collections.exists(self.collection_name):
            self.client.collections.delete(self.collection_name)
        self.col = self.client.collections.create(
            self.collection_name,
            vector_config=Configure.Vectors.self_provided(
                vector_index_config=Configure.VectorIndex.hnsw(distance_metric=VectorDistances.COSINE,
                                                               ef=self.ef_search)),
            properties=[Property(name="chunk_id", data_type=DataType.TEXT),
                        Property(name="doc_type", data_type=DataType.TEXT, skip_vectorization=True)],
        )

    def add(self, ids, vectors, metadatas) -> None:
        with self.col.batch.fixed_size(batch_size=200) as batch:
            for i, v, m in zip(ids, vectors, metadatas):
                batch.add_object(properties={"chunk_id": i, "doc_type": m.get("doc_type", "")}, vector=v.tolist(),
                                 uuid=str(uuid.uuid5(uuid.NAMESPACE_URL, i)))
        if self.col.batch.failed_objects:
            raise RuntimeError(f"Weaviate 색인 실패 {len(self.col.batch.failed_objects)}건")

    def search(self, vector, k, filter=None):
        from weaviate.classes.query import Filter, MetadataQuery
        wf = None
        for f, v in (filter or {}).items():
            c = Filter.by_property(f).equal(v)
            wf = c if wf is None else wf & c
        r = self.col.query.near_vector(near_vector=vector.tolist(), limit=k, filters=wf,
                                       return_metadata=MetadataQuery(distance=True))
        return [(o.properties["chunk_id"], 1.0 - o.metadata.distance) for o in r.objects]

    def __del__(self):
        try:
            self.client.close()
        except Exception:
            pass
