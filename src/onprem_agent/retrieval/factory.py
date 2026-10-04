"""설정(dict/YAML)으로 검색 갈래를 조립한다. 비교 실험은 설정 파일만 바꿔서 돌린다."""

from __future__ import annotations

from ..embed import make_embedder
from ..stores import make_store
from .bm25 import BM25Retriever
from .dense import DenseRetriever
from .hybrid import HybridRetriever

_embedder_cache: dict[str, object] = {}


def _embedder(spec: dict):
    key = repr(sorted(spec.items()))
    if key not in _embedder_cache:  # 같은 모델을 여러 갈래에서 쓸 때 한 번만 로드
        _embedder_cache[key] = make_embedder(spec)
    return _embedder_cache[key]


def build_retriever(spec: dict, defaults: dict | None = None):
    defaults = defaults or {}
    kind = spec["kind"]
    if kind == "bm25":
        return BM25Retriever(**spec.get("params", {}))
    if kind == "dense":
        emb = spec.get("embedder", defaults.get("embedder", {"kind": "hash"}))
        return DenseRetriever(_embedder(emb), make_store(spec.get("store", {"kind": "memory"})),
                              query_prefix=spec.get("query_prefix", ""))
    if kind == "hybrid":
        parts = [build_retriever(p, defaults) for p in spec["parts"]]
        return HybridRetriever(parts, fetch_k=spec.get("fetch_k", 20), rrf_k=spec.get("rrf_k", 60))
    raise ValueError(f"알 수 없는 검색 갈래: {kind}")
