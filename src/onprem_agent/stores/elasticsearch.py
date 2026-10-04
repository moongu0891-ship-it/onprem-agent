"""Elasticsearch 어댑터 (dense_vector + HNSW).

국내 기업은 검색 인프라로 Elasticsearch 를 이미 쓰는 경우가 많아, '별도 벡터DB 없이
기존 ES 에 벡터를 얹으면 어떤가'가 실무 질문이다. 본문 필드에는 한국어 형태소 분석기
Nori 를 걸어 두었다 — ES 안에서 BM25 + kNN 을 함께 쓰는 실험(다음 단계)에 쓴다.
Nori 가 없는 이미지면 analyzer: standard 로 바꾼다.
"""

from __future__ import annotations


class ElasticsearchStore:
    name = "elasticsearch"

    def __init__(self, url: str = "http://localhost:9200", index: str = "chunks",
                 analyzer: str = "nori", num_candidates: int = 128, hnsw_m: int = 16, ef_construct: int = 100):
        from elasticsearch import Elasticsearch
        self.es = Elasticsearch(url, request_timeout=120)
        self.index = index
        self.analyzer = analyzer
        self.num_candidates = num_candidates
        self.hnsw = (hnsw_m, ef_construct)

    def reset(self, dim: int) -> None:
        self.es.indices.delete(index=self.index, ignore_unavailable=True)
        self.es.indices.create(index=self.index, mappings={"properties": {
            "chunk_id": {"type": "keyword"},
            "section_id": {"type": "keyword"},
            "doc_type": {"type": "keyword"},
            "text": {"type": "text", "analyzer": self.analyzer},
            "vec": {"type": "dense_vector", "dims": dim, "index": True, "similarity": "cosine",
                    "index_options": {"type": "hnsw", "m": self.hnsw[0], "ef_construction": self.hnsw[1]}},
        }})

    def add(self, ids, vectors, metadatas) -> None:
        from elasticsearch.helpers import bulk
        actions = ({"_index": self.index, "_id": i,
                    "_source": {"chunk_id": i, "section_id": m.get("section_id"), "doc_type": m.get("doc_type"),
                                "text": m.get("text", ""),
                                "vec": v.tolist()}}
                   for i, v, m in zip(ids, vectors, metadatas))
        bulk(self.es, actions, chunk_size=500)
        self.es.indices.refresh(index=self.index)

    def search(self, vector, k, filter=None):
        knn = {"field": "vec", "query_vector": vector.tolist(), "k": k, "num_candidates": max(self.num_candidates, k)}
        if filter:  # knn 안의 filter 는 근사 탐색 중에 적용된다 (탐색 후에 거르는 방식이 아님)
            knn["filter"] = {"bool": {"must": [{"term": {f: v}} for f, v in filter.items()]}}
        r = self.es.search(index=self.index, size=k, source=["chunk_id"], knn=knn)
        # ES cosine 점수 = (1 + cos) / 2 → 원래 코사인으로 되돌린다
        return [(h["_source"]["chunk_id"], 2 * h["_score"] - 1) for h in r["hits"]["hits"]]
