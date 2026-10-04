"""벡터 검색: 임베더(무엇으로 숫자로 바꾸나) × 저장소(어디에 두고 찾나)."""

from __future__ import annotations

from ..corpus import Chunk
from ..embed import Embedder
from ..stores import VectorStore
from .base import Hit


class DenseRetriever:
    def __init__(self, embedder: Embedder, store: VectorStore, query_prefix: str = ""):
        self.embedder = embedder
        self.store = store
        self.query_prefix = query_prefix
        self.name = f"dense[{embedder.name}·{store.name}]"

    def index(self, chunks: list[Chunk]) -> None:
        self.by_id = {c.chunk_id: c for c in chunks}
        vecs = self.embedder.embed([c.text for c in chunks])
        self.store.reset(vecs.shape[1])
        self.store.add([c.chunk_id for c in chunks], vecs,
                       [{"section_id": c.section_id, "doc": c.doc} for c in chunks])

    def search(self, query: str, k: int) -> list[Hit]:
        q = self.embedder.embed([self.query_prefix + query])[0]
        return [Hit(cid, self.by_id[cid].section_id, s) for cid, s in self.store.search(q, k)]
