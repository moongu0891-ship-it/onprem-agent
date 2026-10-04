"""BM25 (Okapi) 직접 구현. 글자가 겹치는 정도로 점수를 낸다 — 학습하지 않는다."""

from __future__ import annotations

import math
from collections import Counter

from ..corpus import Chunk
from ..tokenize_ko import tokenize
from .base import Hit


class BM25Retriever:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.name = "bm25"

    def index(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.doc_types = [c.doc_type for c in chunks]
        self.tfs = [Counter(tokenize(c.text)) for c in chunks]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avglen = sum(self.lens) / len(self.lens)
        df = Counter()
        for tf in self.tfs:
            df.update(tf.keys())
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def search(self, query: str, k: int, filter: dict | None = None) -> list[Hit]:
        q = [t for t in tokenize(query) if t in self.idf]
        want = (filter or {}).get("doc_type")
        scores = []
        for i, tf in enumerate(self.tfs):
            s = 0.0
            if want and self.doc_types[i] != want:
                scores.append(0.0)
                continue
            norm = self.k1 * (1 - self.b + self.b * self.lens[i] / self.avglen)
            for t in q:
                f = tf.get(t, 0)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + norm)
            scores.append(s)
        top = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        return [Hit(self.chunks[i].chunk_id, self.chunks[i].section_id, scores[i]) for i in top if scores[i] > 0]
