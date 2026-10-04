"""벡터 검색: 임베더(무엇으로 숫자로 바꾸나) × 저장소(어디에 두고 찾나).

저장소끼리 비교할 때는 같은 벡터를 써야 공정하다. 그래서 문서 임베딩은
(임베더, 문서 묶음) 단위로 한 번만 계산해 캐시하고, 시간도
'임베딩'과 '저장소 적재'를 나눠 잰다.
"""

from __future__ import annotations

import hashlib
import time

import numpy as np

from ..corpus import Chunk
from ..embed import Embedder
from ..stores import VectorStore
from .base import Hit

_vec_cache: dict[tuple[str, str], object] = {}


def _corpus_key(chunks: list[Chunk]) -> str:
    h = hashlib.sha1()
    for c in chunks:
        h.update(c.chunk_id.encode())
        h.update(c.text.encode())
    return h.hexdigest()


class DenseRetriever:
    def __init__(self, embedder: Embedder, store: VectorStore, query_prefix: str = ""):
        self.embedder = embedder
        self.store = store
        self.query_prefix = query_prefix
        self.name = f"dense[{embedder.name}·{store.name}]"
        self.timings: dict[str, float] = {}
        self.store_latencies_ms: list[float] = []  # 질의 임베딩을 뺀, 저장소 검색만의 지연
        self.ann_recalls: list[float] = []  # 근사 재현율: 정확 검색(전수 비교) 상위 10개를 몇 % 되찾았나

    def index(self, chunks: list[Chunk]) -> None:
        self.by_id = {c.chunk_id: c for c in chunks}
        key = (self.embedder.name, _corpus_key(chunks))
        t0 = time.perf_counter()
        if key not in _vec_cache:
            _vec_cache[key] = self.embedder.embed([c.text for c in chunks])
        vecs = _vec_cache[key]
        self._vecs, self._ids = vecs, [c.chunk_id for c in chunks]
        t1 = time.perf_counter()
        self.store.reset(vecs.shape[1])
        self.store.add([c.chunk_id for c in chunks], vecs,
                       [{"section_id": c.section_id, "doc": c.doc, "text": c.text} for c in chunks])
        self.store_latencies_ms = []
        self.ann_recalls = []
        self.timings = {"embed_s": t1 - t0, "store_add_s": time.perf_counter() - t1}

    def search(self, query: str, k: int) -> list[Hit]:
        q = self.embedder.embed([self.query_prefix + query])[0]
        t = time.perf_counter()
        found = self.store.search(q, k)
        self.store_latencies_ms.append((time.perf_counter() - t) * 1000)
        if k >= 10:  # 시간 측정 밖에서, 전수 비교 상위 10개와 겹치는 비율을 잰다
            exact = {self._ids[i] for i in np.argsort(-(self._vecs @ q))[:10]}
            self.ann_recalls.append(len(exact & {cid for cid, _ in found[:10]}) / 10)
        return [Hit(cid, self.by_id[cid].section_id, s) for cid, s in found]
