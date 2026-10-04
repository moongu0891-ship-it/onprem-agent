"""질문 의도로 문서 종류 필터를 고른다.

'CRB-03 조치 순서' 는 매뉴얼을, '2025년 5월 4호기 CRB-01 때 뭘 했지?' 는 작업 이력을 찾아야 한다.
2주차 측정에서 남은 오답은 거의 다 '매뉴얼을 물었는데 같은 코드를 쓴 이력이 올라온' 경우였다.

규칙 기반으로 시작한다: 날짜·호기·과거형 표현이 있으면 이력, 아니면 매뉴얼.
규칙이 틀리면 정답을 아예 못 찾게 되므로(필터는 되돌릴 수 없는 결정), 오분류율을 따로 잰다.
"""

from __future__ import annotations

import re

from ..corpus import Chunk
from .base import Hit, Retriever

# 1차 규칙의 오분류 4/78 에서 고친 것:
#  - '\d+ 월' 은 'PLN-LT33 월 요금'을 날짜로 읽었다 → 숫자와 '월'이 붙어 있을 때만 (5월, 12월)
#  - '언제' 는 '스트레이너 언제 청소해?' 같은 매뉴얼 질문에도 흔하다 → 제외
HISTORY_RE = re.compile(r"\d{4}\s*년|(?<![\w-])\d{1,2}월|\d+\s*호기|이력|기록|지난|했었|했던")


def classify(query: str) -> str:
    return "work_order" if HISTORY_RE.search(query) else "manual"


class IntentFilterRetriever:
    def __init__(self, inner: Retriever):
        self.inner = inner
        self.name = f"intent[{inner.name}]"
        self.decisions: list[tuple[str, str]] = []

    def index(self, chunks: list[Chunk]) -> None:
        self.inner.index(chunks)
        self.decisions = []

    def search(self, query: str, k: int, filter: dict | None = None) -> list[Hit]:
        doc_type = classify(query)
        self.decisions.append((query, doc_type))
        return self.inner.search(query, k, {**(filter or {}), "doc_type": doc_type})
