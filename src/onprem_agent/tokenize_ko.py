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


@lru_cache(maxsize=1)
def _kiwi():
    from kiwipiepy import Kiwi
    return Kiwi()


def tokenize(text: str) -> list[str]:
    codes = [c.lower() for c in CODE_RE.findall(text)]
    rest = CODE_RE.sub(" ", text)
    tokens = [
        t.form.lower()
        for t in _kiwi().tokenize(rest)
        if t.tag.startswith(_KEEP_TAGS)
    ]
    return codes + tokens
