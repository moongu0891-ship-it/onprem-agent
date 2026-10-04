# onprem-agent

**폐쇄망에서 도는 엔터프라이즈 에이전트 레퍼런스 구현.**
서빙 엔진(vLLM · SGLang · llama.cpp), 벡터DB(Qdrant · Milvus · Elasticsearch · Weaviate · pgvector), 에이전트(LangGraph + MCP)를
**같은 평가셋으로 재서 비교하고, 그 근거로 고른다.**

> "X를 써 봤다"가 아니라 "X와 Y를 이 조건에서 재 보고 이걸 골랐다"를 보여 주는 저장소입니다.

## 왜 이렇게 만드나

- 에이전트를 실제 현장에 넣는 회사들은 대부분 여러 고객사·계열사에 **같은 엔진을 다른 데이터로** 깐다. 그래서 엔진과 도메인을 분리하고, 도메인 두 개로 교체를 실증한다.
- 고객사마다 쓰는 벡터DB와 서빙 엔진이 다르다. 하나를 깊게 쓰기보다 **공통 인터페이스 뒤에 여러 개를 두고 숫자로 비교**한다.
- 설비 매뉴얼·고객 정보는 외부 반출이 안 되는 경우가 많다. 모든 계층이 **사내망 안에서** 돌아야 한다.

## 계층 구성

| 계층 | 구성 | 비교 대상 |
|---|---|---|
| 시나리오 | ① 운영 장애 대응(설비 경보 → 진단 → 매뉴얼 조치) ② 고객 상담(요금제·약관 + 고객 DB) | 엔진은 그대로, 도메인만 교체 |
| 에이전트 | LangGraph, 도구는 MCP 서버 (SQL 조회 · 문서 검색 · 분석 모델 · 승인 필요한 실행) | 모델·설정별 과업 성공률 |
| 검색 | 하이브리드(BM25 + 벡터, RRF) + 리랭커, 한국어 토큰화 | Qdrant · Milvus · Elasticsearch · Weaviate · pgvector (+ Chroma) |
| 서빙 | OpenAI 호환 API, LiteLLM 게이트웨이로 한 주소 | vLLM · SGLang (GPU) · llama.cpp (CPU) |
| 공통 | 평가 하네스 · 가드레일 · Langfuse 추적 · K8s · CI/CD · 오프라인 설치 | |

진행 상황은 [docs/ROADMAP.md](docs/ROADMAP.md).

## 1주차 결과: 검색 기준선

`configs/retrieval_baseline.yaml` — 모델 다운로드 없이 어디서나 돈다(CI 회귀 검사용). 전체 표: [reports/retrieval_baseline.md](reports/retrieval_baseline.md)

| 시나리오 | 갈래 | 코드 질문 R@3 | 바꿔 말하기 R@3 | 어려운 질문 R@3 |
|---|---|---|---|---|
| 운영 장애 | BM25 | 1.00 | 1.00 | 0.50 |
| 운영 장애 | 해시 벡터(기준선) | 0.77 | 0.75 | 0.38 |
| 고객 상담 | BM25 | 1.00 | 0.93 | 0.62 |
| 고객 상담 | 해시 벡터(기준선) | 1.00 | 0.83 | 0.56 |

- **코드 질문**(`CRB-03 조치 순서`): 경보 코드 32종 중 다수가 한 글자만 다르다. 글자로 찾는 BM25 가 강하다.
- **어려운 질문**(`회전체 쪽 떨림이 날마다 조금씩 심해져` → 진동 드리프트 DRF-08): 문서와 낱말이 겹치지 않는다. BM25 가 절반을 놓친다.
- 해시 벡터는 '뜻'을 모르는 배선 확인용 기준선이다. 실제 의미 임베딩(bge-m3)이 어려운 질문을 얼마나 끌어올리는지가 다음 측정이다 → `configs/retrieval_bge.yaml`

## 실행

```bash
pip install -e ".[chroma,dev]"
python scripts/make_data.py                                   # 가상 데이터·평가셋 생성 (결정적)
python scripts/eval_retrieval.py configs/retrieval_baseline.yaml --min-recall3 0.80
pytest -q

# 실제 임베딩 모델로 (bge-m3 약 2.3GB, 첫 실행 때 내려받음)
pip install -e ".[st]"
python scripts/eval_retrieval.py configs/retrieval_bge.yaml
```

## 구조

```
src/onprem_agent/
  corpus.py         문서 → 절(id) → 청크. 정답은 절 id 로 적어 청크 크기를 바꿔도 평가셋이 그대로 쓰인다
  tokenize_ko.py    Kiwi 형태소 분석 + 코드형 토큰(CRB-03, PLN-5G55) 통째 보존
  embed.py          임베더 교체 지점: hash · sentence-transformers · OpenAI 호환(vLLM/Ollama)
  stores/           벡터DB 어댑터 (같은 VectorStore 인터페이스)
  retrieval/        BM25 · 벡터 · 하이브리드(RRF), 설정으로 조립
  eval/             Recall@k · MRR · 지연 p50/p95, 질문 유형별 채점, 마크다운 리포트
configs/            실험 설정 (실험은 설정 파일만 바꿔서 돌린다)
data/ ops · cs      가상 설비 매뉴얼, 가상 통신사 요금제·약관·FAQ, 가상 고객 DB
eval/               질문셋 (유형: code · paraphrase · hard, 정답 = 절 id)
```

## 평가 원칙

1. 한 실험에서 바뀌는 것은 하나뿐이다. 문서, 청킹, 질문, k 는 고정.
2. 질문 유형별로 따로 채점한다. 평균 하나로 뭉치면 약점이 숨는다.
3. 정확도와 함께 색인 시간·지연(p50/p95)을 잰다.
4. 데이터는 생성 스크립트로 만들고, CI 가 스크립트와 커밋된 데이터가 일치하는지 확인한다.

> 모든 회사·제품·인물·전화번호는 가상입니다.
