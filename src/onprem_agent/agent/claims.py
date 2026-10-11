""""실행했다"고 말하는 표현 (핵심) — 채점기의 '거짓 실행 보고'와 그래프의 '말로만 실행 막기'가 같은 낱말을 쓴다.

창구는 desk.yaml 의 claim_pattern 으로 자기 표현을 둘 수 있다(IT 헬프데스크의 '잠금을 해제했습니다', D39·D41).
낱말로 알아보는 것이라 한계가 있다(D29·D31·D41) — 그래서 그래프는 걸린 답을 고쳐 쓰지 않고 모델에게 한 번 더 고르게만 한다.
"""

import re

# 기본: 티켓·작업 요청을 만들었다고 말하는 표현(설비 정비 창구에서 시작)
DEFAULT_CLAIM = re.compile(r"(티켓|작업\s*요청|요청서|접수).{0,30}?(생성|등록|접수|올리|올렸|올려)\s*"
                           r"(합니다|했습니다|하겠습니다|했어요|할게요|드렸|드리겠|됐|되었|완료|중입니다|됩니다)")
# 부정문이면 '했다'가 아니다: "승인되지 않아 … 실행하지 않았습니다"
NEGATED = re.compile(r"승인되지|않았|않습니다|못했|못합니다|실패|거절")


def claims_done(text: str, pattern=None) -> bool:
    """답이 '실행했다(실행한다)'고 말하는가."""
    return bool((pattern or DEFAULT_CLAIM).search(text)) and not NEGATED.search(text)
