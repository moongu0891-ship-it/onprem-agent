from pathlib import Path

from onprem_agent.corpus import chunk_text, load_corpus, split_sections
from onprem_agent.eval.metrics import mrr, recall_at_k
from onprem_agent.retrieval import BM25Retriever, Hit, rrf_fuse
from onprem_agent.tokenize_ko import tokenize

ROOT = Path(__file__).resolve().parents[1]


def test_code_tokens_are_kept_whole():
    toks = tokenize("CRB-03 경보와 SPK-03 경보")
    assert "crb-03" in toks and "spk-03" in toks
    assert "03" not in toks  # 쪼개지면 두 코드가 '03'으로 겹친다


def test_particles_are_dropped():
    assert tokenize("밸브를") == tokenize("밸브의") == ["밸브"]


def test_split_sections_requires_id():
    md = "## A\n<!-- id: X-1 -->\n본문1\n\n## 목차\n아무거나\n"
    assert [s[0] for s in split_sections(md)] == ["X-1"]


def test_chunk_text_respects_limit():
    text = "\n\n".join("가" * 250 for _ in range(5))
    pieces = chunk_text(text, max_chars=600, overlap=50)
    assert len(pieces) > 1 and all(len(p) <= 600 + 50 + 2 for p in pieces)


def test_rrf_prefers_items_ranked_high_in_both():
    a = [Hit("x#0", "X", 9), Hit("y#0", "Y", 8)]
    b = [Hit("y#0", "Y", 0.9), Hit("z#0", "Z", 0.8)]
    assert rrf_fuse([a, b])[0].chunk_id == "y#0"


def test_metrics_count_sections_once():
    ranked = ["A", "A", "B", "C"]
    assert recall_at_k(ranked, ["B"], 2) == 1.0
    assert mrr(ranked, ["C"]) == 1 / 3


def test_bm25_separates_one_char_codes():
    chunks = load_corpus(ROOT / "data/ops")
    r = BM25Retriever()
    r.index(chunks)
    for code in ("CRB-03", "CRB-04", "SPK-03"):
        assert r.search(f"{code} 조치", 1)[0].section_id == f"OPS-{code}"


def test_rrf_weights_can_overrule_a_branch():
    a = [Hit("x#0", "X", 9)]
    b = [Hit("y#0", "Y", 0.9)]
    assert rrf_fuse([a, b], weights=[0.3, 1.0])[0].chunk_id == "y#0"


def test_routed_sends_code_queries_to_code_route():
    from onprem_agent.retrieval import RoutedRetriever

    class Fixed:
        def __init__(self, sid):
            self.name, self.sid = sid, sid

        def index(self, chunks):
            pass

        def search(self, q, k, filter=None):
            return [Hit(self.sid + "#0", self.sid, 1.0)]

    r = RoutedRetriever(Fixed("CODE"), Fixed("DEFAULT"))
    assert r.search("CRB-03 조치", 1)[0].section_id == "CODE"
    assert r.search("떨림이 심해져", 1)[0].section_id == "DEFAULT"


def test_intent_classifier():
    from onprem_agent.retrieval.intent import classify
    assert classify("CRB-03 조치 순서 알려줘") == "manual"
    assert classify("설비 만지기 전에 뭘 먼저 해야 하나요?") == "manual"
    assert classify("2025년 5월에 4호기 CRB-01 경보 났을 때 어떤 조치를 했었지?") == "work_order"


def test_filters_respected_by_bm25_and_memory_store():
    from onprem_agent.retrieval import build_retriever
    chunks = load_corpus(ROOT / "data/ops") + load_corpus(ROOT / "data/ops_logs")
    for spec in ({"kind": "bm25"}, {"kind": "dense", "store": {"kind": "memory"}}):
        r = build_retriever(spec, {"embedder": {"kind": "hash"}})
        r.index(chunks)
        by_id = {c.chunk_id: c for c in chunks}
        for dt in ("manual", "work_order"):
            hits = r.search("CRB-03 경보 조치", 10, {"doc_type": dt})
            assert hits and all(by_id[h.chunk_id].doc_type == dt for h in hits)


def test_reranker_reorders_candidates():
    from onprem_agent.retrieval import build_retriever
    chunks = load_corpus(ROOT / "data/ops")
    r = build_retriever({"kind": "rerank", "scorer": {"kind": "overlap"}, "fetch_k": 20,
                         "inner": {"kind": "dense", "store": {"kind": "memory"}}}, {"embedder": {"kind": "hash"}})
    r.index(chunks)
    hits = r.search("베어링 교체", 3)
    assert len(hits) == 3 and hits[0].score >= hits[-1].score


def test_dates_and_lines_normalize_to_same_token():
    q = tokenize("2025년 7월 1호기 LVL-06 이력")
    d = tokenize("2025-07-14 KX-200 1호기에서 LVL-06 경보 발생")
    for t in ("2025-07", "1호기", "lvl-06"):
        assert t in q and t in d
