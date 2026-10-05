"""에이전트가 쓸 업무 기능(도구) 정의 (OpenAI tools 형식).

5~6주차 에이전트가 실제로 쓸 업무 기능(도구)과 같은 모양이다. 서빙 측정에서는 두 군데 쓴다.
- 부하 측정: 시스템 프롬프트에 업무 기능(도구) 설명을 넣어, 실제 에이전트처럼 '모든 요청이 같은 긴 앞부분'을 갖게 한다.
- 업무 기능(도구) 호출 검사: 엔진마다 tools 파라미터로 넘겨 올바른 업무 기능(도구)·인자를 고르는지 본다.
"""

TOOLS = [
    {"type": "function", "function": {
        "name": "search_manual",
        "description": "KX-200 설비 매뉴얼에서 경보 코드의 의미, 조치 순서, 안전 수칙, 부품 정보를 찾는다. "
                       "'어떻게 해야 하나', '무슨 뜻인가' 처럼 절차·설명을 묻는 질문에 쓴다.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "검색할 내용. 경보 코드가 있으면 그대로 넣는다."}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "get_work_orders",
        "description": "정비 작업 이력을 조회한다. 특정 호기·경보 코드·연월에 무슨 일이 있었고 어떻게 처리했는지 묻는 질문에 쓴다.",
        "parameters": {"type": "object", "properties": {
            "line": {"type": "integer", "description": "설비 호기 번호 (1~6)"},
            "alarm_code": {"type": "string", "description": "경보 코드, 예: LVL-06"},
            "month": {"type": "string", "description": "연월 YYYY-MM, 예: 2025-07"}},
            "required": ["line", "alarm_code", "month"]}}},
    {"type": "function", "function": {
        "name": "create_ticket",
        "description": "정비 작업 요청 티켓을 만든다. 사용자가 작업 요청·티켓 생성·등록을 명시적으로 요구할 때만 쓴다. "
                       "실행 전 사람의 승인이 필요하다.",
        "parameters": {"type": "object", "properties": {
            "line": {"type": "integer", "description": "설비 호기 번호 (1~6)"},
            "alarm_code": {"type": "string"},
            "summary": {"type": "string", "description": "작업 내용 한 줄 요약"},
            "priority": {"type": "string", "enum": ["low", "normal", "high"],
                         "description": "긴급하면 high, 급하지 않으면 low, 언급 없으면 normal"}},
            "required": ["line", "alarm_code", "summary", "priority"]}}},
    {"type": "function", "function": {
        "name": "get_customer",
        "description": "고객 번호로 고객의 요금제, 약정, 미납 금액, 로밍 상품을 조회한다.",
        "parameters": {"type": "object", "properties": {
            "customer_id": {"type": "string", "description": "고객 번호, 예: C0012"}},
            "required": ["customer_id"]}}},
    {"type": "function", "function": {
        "name": "get_plan",
        "description": "요금제 코드로 요금제의 월 요금, 데이터 제공량, 부가 혜택을 조회한다.",
        "parameters": {"type": "object", "properties": {
            "plan_code": {"type": "string", "description": "요금제 코드, 예: PLN-5G59"}},
            "required": ["plan_code"]}}},
]
