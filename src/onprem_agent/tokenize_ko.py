"""BM25용 한국어 토큰화.

두 가지를 함께 한다.
1) 경보 코드·요금제 코드처럼 '한 글자만 달라도 다른 것'은 통째로 보존한다.
   Kiwi는 `CRB-03`을 `CRB`·`-`·`03`으로 쪼개서, 그대로 두면 `SPK-03`과 `03`이 겹친다.
2) 나머지는 Kiwi 형태소 분석으로 내용어(명사·동사·형용사 어간·외래어·숫자)만 남긴다.
   조사·어미를 버려서 「밸브를」과 「밸브의」가 같은 토큰이 되게 한다.
"""

from __future__ import annotations

import re
from functools import lru_cache

# 대문자 2~5자 + 하이픈 + 숫자/문자 (CRB-03, ERR-302, P0301 같은 품번은 별도 규칙)
CODE_RE = re.compile(r"\b[A-Z]{2,5}-[A-Z0-9]{2,4}\b|\b[A-Z]\d{4}\b")

_KEEP_TAGS = ("NN", "VV", "VA", "SL", "SN", "XR", "SH")

# 3) 날짜·호기는 쓰는 방식이 달라도 같은 토큰이 되게 맞춘다.
#    질문 "2025년 7월 1호기" ↔ 문서 "2025-07-14 … 1호기". 그대로 쪼개면 '7' 과 '07' 이 다른 낱말이 되어
#    BM25 가 이력 질문을 한 개도 못 찾았다(이력 질문 R@3 0.00, 2주차 측정).
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-\d{1,2}\b")
_DATE_KO = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월")
_LINE = re.compile(r"(\d+)\s*호기")


@lru_cache(maxsize=1)
def _kiwi():
    from kiwipiepy import Kiwi
    return Kiwi()


def tokenize(text: str) -> list[str]:
    norm = [f"{y}-{int(m):02d}" for y, m in _DATE_ISO.findall(text) + _DATE_KO.findall(text)]
    norm += [f"{n}호기" for n in _LINE.findall(text)]
    text = _LINE.sub(" ", _DATE_KO.sub(" ", _DATE_ISO.sub(" ", text)))
    codes = [c.lower() for c in CODE_RE.findall(text)] + norm
    rest = CODE_RE.sub(" ", text)
    tokens = [
        t.form.lower()
        for t in _kiwi().tokenize(rest)
        if t.tag.startswith(_KEEP_TAGS)
    ]
    return codes + tokens
