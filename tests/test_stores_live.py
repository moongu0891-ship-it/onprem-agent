"""실제 DB 서버가 떠 있을 때만 도는 통합 테스트.

    ONPREM_LIVE_STORES=qdrant,pgvector,elasticsearch,weaviate,milvus pytest -q tests/test_stores_live.py

각 어댑터가 정답 상한(memory, 전수 비교)과 같은 1등을 내는지, 근사 재현율이 충분한지 본다.
CI 에서는 GitHub Actions 서비스 컨테이너로 qdrant·pgvector·elasticsearch·weaviate 를 띄워 돌린다.
"""

import os
from pathlib import Path

import pytest

from onprem_agent.corpus import load_corpus
from onprem_agent.retrieval import build_retriever

ROOT = Path(__file__).resolve().parents[1]
LIVE = [s for s in os.environ.get("ONPREM_LIVE_STORES", "").split(",") if s]

SPECS = {
    "qdrant": {"kind": "qdrant", "url": os.environ.get("QDRANT_URL", "http://localhost:6333")},
    "milvus": {"kind": "milvus", "uri": os.environ.get("MILVUS_URI", "http://localhost:19530")},
    "elasticsearch": {"kind": "elasticsearch", "url": os.environ.get("ES_URL", "http://localhost:9200"),
                      "analyzer": os.environ.get("ES_ANALYZER", "nori")},
    "weaviate": {"kind": "weaviate"},
    "pgvector": {"kind": "pgvector", "dsn": os.environ.get("PG_DSN", "postgresql://agent:agent@localhost:5432/agent")},
}

QUERIES = ["CRB-03 조치 순서", "설비 만지기 전에 뭘 먼저 해야 하나요?", "밸브 응답 없음", "베어링 교체"]


@pytest.fixture(scope="module")
def chunks():
    return load_corpus(ROOT / "data/ops")


@pytest.mark.parametrize("store", LIVE or [pytest.param("none", marks=pytest.mark.skip("ONPREM_LIVE_STORES 미설정"))])
def test_store_matches_exact_search(store, chunks):
    defaults = {"embedder": {"kind": "hash", "dim": 512}}
    exact = build_retriever({"kind": "dense", "store": {"kind": "memory"}}, defaults)
    live = build_retriever({"kind": "dense", "store": SPECS[store]}, defaults)
    exact.index(chunks)
    live.index(chunks)
    for q in QUERIES:
        assert live.search(q, 10)[0].chunk_id == exact.search(q, 10)[0].chunk_id, q
    assert sum(live.ann_recalls) / len(live.ann_recalls) >= 0.9


@pytest.mark.parametrize("store", LIVE or [pytest.param("none", marks=pytest.mark.skip("ONPREM_LIVE_STORES 미설정"))])
def test_store_filter_returns_only_requested_doc_type(store):
    # 매뉴얼 45절 + 작업 이력 2,400건: 매뉴얼은 1.8% 뿐이라 '탐색 후 거르기' 방식이면 결과가 비기 쉽다
    chunks = load_corpus(ROOT / "data/ops") + load_corpus(ROOT / "data/ops_logs")
    by_id = {c.chunk_id: c for c in chunks}
    live = build_retriever({"kind": "dense", "store": SPECS[store]}, {"embedder": {"kind": "hash", "dim": 512}})
    live.index(chunks)
    for dt in ("manual", "work_order"):
        hits = live.search("CRB-03 경보 조치 순서", 10, {"doc_type": dt})
        assert len(hits) == 10, f"{store}: {dt} 필터 결과 {len(hits)}개"
        assert all(by_id[h.chunk_id].doc_type == dt for h in hits)
