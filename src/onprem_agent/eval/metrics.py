"""검색 평가 지표. 정답 단위는 절(section) id.

같은 절에서 나온 청크가 여러 개 걸려도 한 번만 센다 — 사용자에게 의미 있는 건
'정답 절이 상위 k개 안에 들어왔나' 이기 때문이다.
"""

from __future__ import annotations

import math


def dedup_sections(section_ids: list[str]) -> list[str]:
    seen, out = set(), []
    for s in section_ids:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def recall_at_k(ranked_sections: list[str], gold: list[str], k: int) -> float:
    """정답 절 중 상위 k개(중복 제거 후) 안에 들어온 비율."""
    top = set(dedup_sections(ranked_sections)[:k])
    return sum(g in top for g in gold) / len(gold)


def mrr(ranked_sections: list[str], gold: list[str]) -> float:
    """첫 정답이 몇 번째에 나왔는지의 역수. 못 찾으면 0."""
    for rank, s in enumerate(dedup_sections(ranked_sections), start=1):
        if s in gold:
            return 1.0 / rank
    return 0.0


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    v = sorted(values)
    idx = (len(v) - 1) * p / 100
    lo, hi = math.floor(idx), math.ceil(idx)
    return v[lo] + (v[hi] - v[lo]) * (idx - lo)
