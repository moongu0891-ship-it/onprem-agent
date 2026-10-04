"""문서 → 청크.

문서는 마크다운 파일 하나가 '문서', 그 안의 `## ` 제목 하나가 '절(section)'이다.
절에는 `<!-- id: OPS-P019 -->` 처럼 고유 id를 달아 두고, 평가셋의 정답은 이 id로 적는다.
청크는 절을 최대 길이로 잘라 만들며, 모든 청크는 자기가 속한 절 id를 기억한다.
그래서 청크 크기를 바꿔도 정답 표기(절 id)는 그대로 쓸 수 있다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_SECTION_RE = re.compile(r"^## (.+?)\s*$", re.M)
_ID_RE = re.compile(r"<!--\s*id:\s*([\w\-]+)\s*-->")
_DOCTYPE_RE = re.compile(r"<!--\s*doc_type:\s*([\w\-]+)\s*-->")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str          # 예: OPS-P019#0
    section_id: str        # 예: OPS-P019 (평가 정답 단위)
    doc: str               # 원본 파일 이름
    title: str             # 절 제목
    text: str              # 검색·답변에 쓰는 본문 (제목 포함)
    doc_type: str = "manual"  # 문서 종류 (manual | work_order …). 필터 검색에 쓴다
    meta: dict = field(default_factory=dict, compare=False, hash=False)


def split_sections(markdown: str) -> list[tuple[str, str, str]]:
    """마크다운을 (section_id, title, body) 목록으로 나눈다."""
    out = []
    matches = list(_SECTION_RE.finditer(markdown))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        id_m = _ID_RE.search(body)
        if not id_m:
            continue  # id 없는 절은 목차 등으로 보고 건너뛴다
        body = _ID_RE.sub("", body).strip()
        out.append((id_m.group(1), m.group(1).strip(), body))
    return out


def chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """문단 경계를 우선으로 max_chars 이하 조각을 만든다."""
    if len(text) <= max_chars:
        return [text]
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    cur = ""
    for p in paras:
        if len(p) > max_chars:  # 아주 긴 문단은 글자 단위로 자른다
            if cur:
                pieces.append(cur)
                cur = ""
            step = max_chars - overlap
            pieces.extend(p[i:i + max_chars] for i in range(0, len(p), step))
            continue
        if len(cur) + len(p) + 2 <= max_chars:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            pieces.append(cur)
            tail = cur[-overlap:] if overlap else ""
            cur = f"{tail}\n\n{p}" if tail else p
    if cur:
        pieces.append(cur)
    return pieces


def load_corpus(folder: str | Path, max_chars: int = 600, overlap: int = 80) -> list[Chunk]:
    folder = Path(folder)
    chunks: list[Chunk] = []
    for path in sorted(folder.glob("*.md")):
        md = path.read_text(encoding="utf-8")
        dt = _DOCTYPE_RE.search(md.split("\n## ", 1)[0])  # 파일 머리말의 문서 종류 (없으면 manual)
        doc_type = dt.group(1) if dt else "manual"
        for sid, title, body in split_sections(md):
            for j, piece in enumerate(chunk_text(body, max_chars, overlap)):
                chunks.append(Chunk(
                    chunk_id=f"{sid}#{j}",
                    section_id=sid,
                    doc=path.name,
                    title=title,
                    text=f"{title}\n{piece}",
                    doc_type=doc_type,
                ))
    if not chunks:
        raise ValueError(f"{folder} 에서 id가 달린 절을 찾지 못했습니다")
    return chunks
