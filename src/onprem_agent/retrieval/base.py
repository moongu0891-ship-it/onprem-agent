from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..corpus import Chunk


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    section_id: str
    score: float


class Retriever(Protocol):
    name: str

    def index(self, chunks: list[Chunk]) -> None: ...

    def search(self, query: str, k: int, filter: dict | None = None) -> list[Hit]: ...
