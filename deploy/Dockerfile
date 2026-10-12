# 03장: 에이전트 이미지 — 상담 화면(웹) + 에이전트 그래프 + 창구 서버가 한 이미지에. 모델은 밖(07장의 모델 서버)에서 부른다.
#   docker build -f deploy/Dockerfile -t onprem-agent:v1 .
# 한 이미지로 두 역할을 한다(실행 명령만 다름): 상담 화면 `python scripts/web.py`, 전체 시험 `make test-full`(12장).
# 검색 임베더(bge-m3)는 이미지에 넣지 않는다 — 10장에서 PVC 에 받아 두고 마운트한다(이미지가 2GB 커지지 않게).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# 시스템 꾸러미: make(시험 명령), curl(헬스 체크), git(설치 확인용) — 최소만
RUN apt-get update && apt-get install -y --no-install-recommends make curl && rm -rf /var/lib/apt/lists/*

# 의존성 먼저(코드가 바뀌어도 이 층은 캐시에서 재사용)
COPY pyproject.toml ./
COPY src ./src
# st(sentence-transformers, torch 2GB)는 넣지 않는다 — 03~09장은 해시 임베더, 검색 임베더는 10장에서 따로.
RUN pip install -e ".[agent,agent-pg,web,dev]"   # agent-pg: 10장 PostgreSQL 체크포인터 + pgvector

# 코드·창구·데이터·과업·설정 — 상담 화면과 시험이 읽는 것 전부
COPY scripts ./scripts
COPY examples ./examples
COPY data ./data
COPY eval ./eval
COPY configs ./configs
COPY tests ./tests
COPY Makefile ./

# 대화·승인 대기(SQLite)와 결과는 쓰기 가능한 자리에(컨테이너는 읽기 전용으로 돌릴 수 있게)
# 업무 DB(data/*.db, 티켓 등록이 쓴다)·대화 저장(var)·결과(results)에 쓸 수 있어야 하므로 /app 전체를 일반 사용자 몫으로
RUN mkdir -p /app/var /app/results && useradd -m -u 1000 agent && chown -R agent /app
USER agent
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD curl -sf http://127.0.0.1:8080/healthz || exit 1
CMD ["python", "scripts/web.py", "--host", "0.0.0.0", "--port", "8080"]
