"""임베딩 모델 교체 지점.

- hash               : 모델 없이 도는 글자 n-gram 해시 벡터. CI와 배선 확인용 기준선일 뿐 '뜻'은 모른다.
- sentence-transformers : 로컬 모델 직접 로드 (예: BAAI/bge-m3)
- openai             : OpenAI 호환 /v1/embeddings (vLLM, Ollama, TEI 등). 서빙 계층과 같은 방식으로 붙는다.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


def _l2norm(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


class HashEmbedder:
    def __init__(self, dim: int = 512, ngram: tuple[int, int] = (2, 3)):
        self.dim = dim
        self.ngram = ngram
        self.name = f"hash-{dim}"

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        s = " ".join(text.lower().split())
        for n in range(self.ngram[0], self.ngram[1] + 1):
            for i in range(len(s) - n + 1):
                h = int.from_bytes(hashlib.blake2b(s[i:i + n].encode(), digest_size=8).digest(), "little")
                v[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        return v

    def embed(self, texts: list[str]) -> np.ndarray:
        return _l2norm(np.stack([self._vec(t) for t in texts]))


class SentenceTransformerEmbedder:
    def __init__(self, model: str = "BAAI/bge-m3", device: str | None = None, batch_size: int = 16):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model, device=device)
        self.batch_size = batch_size
        self.name = f"st:{model}"

    def embed(self, texts: list[str]) -> np.ndarray:
        m = self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True)
        return np.asarray(m, dtype=np.float32)


class OpenAICompatEmbedder:
    def __init__(self, base_url: str, model: str, api_key: str = "EMPTY", batch_size: int = 32):
        import httpx
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=120,
                                   headers={"Authorization": f"Bearer {api_key}"})
        self.model = model
        self.batch_size = batch_size
        self.name = f"openai:{model}"

    def embed(self, texts: list[str]) -> np.ndarray:
        out = []
        for i in range(0, len(texts), self.batch_size):
            r = self.client.post("/v1/embeddings", json={"model": self.model, "input": texts[i:i + self.batch_size]})
            r.raise_for_status()
            out.extend(d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"]))
        return _l2norm(np.asarray(out, dtype=np.float32))


def make_embedder(spec: dict) -> Embedder:
    kind = spec.get("kind", "hash")
    args = {k: v for k, v in spec.items() if k != "kind"}
    if kind == "hash":
        return HashEmbedder(**args)
    if kind == "sentence-transformers":
        return SentenceTransformerEmbedder(**args)
    if kind == "openai":
        return OpenAICompatEmbedder(**args)
    raise ValueError(f"알 수 없는 임베더: {kind}")
