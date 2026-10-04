"""Milvus 어댑터. uri 가 파일 경로면 Milvus Lite(테스트용), http:// 면 서버(Docker)."""

from __future__ import annotations


class MilvusStore:
    name = "milvus"

    def __init__(self, uri: str = "./milvus_lite.db", collection: str = "chunks",
                 index_type: str = "HNSW", hnsw_m: int = 16, ef_construct: int = 100, ef_search: int = 128):
        from pymilvus import MilvusClient
        self.client = MilvusClient(uri=uri)
        self.collection = collection
        self.index_type = index_type
        self.hnsw = (hnsw_m, ef_construct)
        self.ef_search = ef_search

    def reset(self, dim: int) -> None:
        from pymilvus import DataType
        if self.client.has_collection(self.collection):
            self.client.drop_collection(self.collection)
        schema = self.client.create_schema(auto_id=False)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=128)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dim)
        idx = self.client.prepare_index_params()
        params = {"M": self.hnsw[0], "efConstruction": self.hnsw[1]} if self.index_type == "HNSW" else {}
        idx.add_index(field_name="vector", index_type=self.index_type, metric_type="COSINE", params=params)
        self.client.create_collection(self.collection, schema=schema, index_params=idx)

    def add(self, ids, vectors, metadatas) -> None:
        rows = [{"id": i, "vector": v.tolist()} for i, v in zip(ids, vectors)]
        for s in range(0, len(rows), 1000):
            self.client.insert(self.collection, rows[s:s + 1000])
        self.client.flush(self.collection)
        self.client.load_collection(self.collection)

    def search(self, vector, k):
        params = {"ef": max(self.ef_search, k)} if self.index_type == "HNSW" else {}
        res = self.client.search(self.collection, data=[vector.tolist()], limit=k,
                                 search_params={"metric_type": "COSINE", "params": params})
        return [(h["id"], float(h["distance"])) for h in res[0]]  # COSINE: 클수록 유사
