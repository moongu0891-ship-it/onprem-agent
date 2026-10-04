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
