# 측정 원본

측정기가 낸 결과표를 고르고 해석 문서 링크와 측정 장소를 맨 위에 붙여 커밋한 것이다(측정기는 `results/` 에 쓰고, 그건 Git 에 올리지 않는다).
해석과 결정은 [README](../README.md), [serving/README.md](../serving/README.md), [agent/README.md](../agent/README.md)에 있다.

| 파일 | 무엇 | 어디서 |
|---|---|---|
| [retrieval_baseline.md](retrieval_baseline.md) | 1주차 검색 기준선 (해시 임베더·BM25, CI 회귀 검사와 같은 설정) | 클라우드 작업 환경 |
| [retrieval_bge.md](retrieval_bge.md) | 1주차 bge-m3 · 하이브리드 · 가중 RRF · 코드 라우팅 | 노트북 |
| [retrieval_scale_local.md](retrieval_scale_local.md) | 2주차 문서 규모 확대 후 배선 확인 (모델 없음) | 클라우드 작업 환경 |
| [retrieval_vectordb.md](retrieval_vectordb.md) | 2주차 검색 방식 · 벡터DB 6종 (같은 HNSW 설정) | 노트북 |
| [retrieval_vectordb_hnsw.md](retrieval_vectordb_hnsw.md) | 2주차 pgvector·Chroma HNSW 확대, 3회 반복 | 노트북 |
| [retrieval_filter_rerank.md](retrieval_filter_rerank.md) | 2주차 의도 필터 · 리랭커 · 날짜 표기 · DB별 필터 검색 | 노트북 |
| [serving_laptop.md](serving_laptop.md) | 3주차 vLLM · SGLang · llama.cpp · 캐시 끔 · LiteLLM, 업무 기능(도구) 호출 20문항 | 노트북 |
| [serving_sglang_graph.md](serving_sglang_graph.md) | 3주차 SGLang CUDA 그래프 상한 8 대 16 | 노트북 |
| [failover.md](failover.md) | 3주차 장애 대체 (1순위 정상 종료) | 노트북 |
| [failover_kill.md](failover_kill.md) | 3주차 장애 대체 (1순위 강제 종료, 갑작스러운 고장) | 노트북 |
| [agent_laptop_v1.md](agent_laptop_v1.md) | 4주차 에이전트 과업 26개: 규칙 · Qwen3-1.7B(SGLang·vLLM) · 4B, 실패 답 발췌 (개선 전) | 노트북 |
| [agent_laptop_v2.md](agent_laptop_v2.md) | 4주차 에이전트 2차: 안전 기능 켬/끔 비교, 채점 보강 (측정기 결함 D22 표시) | 노트북 |

노트북 = RTX 5070 Laptop 8GB · WSL2 · Docker.
