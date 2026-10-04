"""설정(dict/YAML)으로 검색 갈래를 조립한다. 비교 실험은 설정 파일만 바꿔서 돌린다."""

from __future__ import annotations

from ..embed import make_embedder
from ..stores import make_store
from .bm25 import BM25Retriever
from .dense import DenseRetriever
from .hybrid import HybridRetriever, RoutedRetriever

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
        return HybridRetriever(parts, fetch_k=spec.get("fetch_k", 20), rrf_k=spec.get("rrf_k", 60),
                               weights=spec.get("weights"))
    if kind == "routed":
        return RoutedRetriever(build_retriever(spec["code_route"], defaults),
                               build_retriever(spec["default_route"], defaults))
    if kind == "intent":
        from .intent import IntentFilterRetriever
        return IntentFilterRetriever(build_retriever(spec["inner"], defaults))
    if kind == "rerank":
        from .rerank import RerankRetriever, cross_encoder_scorer
        sc = spec.get("scorer", {"kind": "cross-encoder"})
        if sc["kind"] == "cross-encoder":
            key = ("ce", sc.get("model", "BAAI/bge-reranker-v2-m3"))
            if key not in _embedder_cache:
                _embedder_cache[key] = cross_encoder_scorer(key[1])
            scorer, sname = _embedder_cache[key], key[1].split("/")[-1]
        elif sc["kind"] == "overlap":  # 테스트·CI 용: 글자 겹침 점수 (모델 없음)
            scorer, sname = _overlap_scorer, "overlap"
        else:
            raise ValueError(f"알 수 없는 점수기: {sc['kind']}")
        return RerankRetriever(build_retriever(spec["inner"], defaults), scorer,
                               fetch_k=spec.get("fetch_k", 30), scorer_name=sname)
    raise ValueError(f"알 수 없는 검색 갈래: {kind}")


def _overlap_scorer(query: str, texts: list[str]) -> list[float]:
    from ..tokenize_ko import tokenize
    q = set(tokenize(query))
    return [len(q & set(tokenize(t))) / (len(q) or 1) for t in texts]
