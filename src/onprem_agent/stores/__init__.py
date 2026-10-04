"""벡터 저장소 어댑터. 모두 같은 VectorStore 인터페이스를 따른다.

1주차: memory(기준선), chroma
2~3주차: qdrant, milvus, elasticsearch, weaviate, pgvector 를 같은 틀에 추가
"""

from .base import VectorStore, make_store

__all__ = ["VectorStore", "make_store"]
