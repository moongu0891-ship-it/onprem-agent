> 측정 기기: 노트북 RTX 5070 Laptop 8GB · WSL2 · Docker (2026-10-04). LiteLLM 1.104.0 · SGLang 0.5.21 · llama.cpp(CPU) server 이미지. 1순위 정상 종료(docker stop) 방식. 해석은 [serving/README.md](../serving/README.md#43-장애-대체-시험-실행-방법-31).
> 주의: '첫 성공까지' 항목은 이 실행 당시 '아무 엔진이든 첫 성공'을 잰 값이다(장애 단계의 0.72초는 1순위가 멈추면서 마저 처리한 요청). 이후 '기다리던 엔진의 첫 응답'을 재도록 고쳤다 (문제해결 이력 D16).

# 장애 대체 시험

- 실행: 2026-10-04T09:59:18+00:00 · 1순위 SGLang (GPU, 그래프≤16) · 대체 llama.cpp (CPU, Q8_0) · 게이트웨이 LiteLLM (`agent-llm`)
- 요청: 짧은 질문, 출력 16토큰, 동시 2개씩 계속 보냄

| 단계 | 요청 | 성공 | 실패 | 답한 엔진 | 지연 p50 (ms) | 지연 p95 (ms) | llama.cpp 처리 토큰 증가 |
|---|---|---|---|---|---|---|---|
| 1 정상 | 28 | 28 | 0 | SGLang 28 | 265 | 3035 | 0 |
| 2 장애 (1순위 멈춤) | 8 | 8 | 0 | SGLang 6, llama.cpp(CPU) 2 | 266 | 12446 | 32 |
| 3a 1순위 재시작 중 | 12 | 12 | 0 | llama.cpp(CPU) 12 | 10969 | 42242 | 192 |
| 3b 1순위 복구 후 | 14 | 14 | 0 | SGLang 14 | 251 | 271 | — |

- 2 장애 (1순위 멈춤): 1순위 멈춤 후 첫 성공까지 0.72 초, 그 뒤 실패 0건
- 3b 1순위 복구 후: 1순위 준비 완료 후 첫 성공까지 15.06 초, 그 뒤 실패 0건

게이트웨이 응답 헤더 예: `x-litellm-call-id=9396f681-e586-4df7-941b-f26f1ea5ac8d, x-litellm-model-id=cb1f9e7c64463547893b515f7c9be3f5cd1c72ecf229bdd563ad9aa1d16f5649, x-litellm-model-name=openai/qwen3-1.7b, x-litellm-model-api-base=http://sglang-g16:30000/v1, x-litellm-version=1.104.0, x-litellm-response-cost-original=0.0, x-litellm-response-cost-discount-amount=0.0, x-litellm-response-cost-margin-amount=0.0, x-litellm-response-cost-margin-percent=0.0, x-litellm-response-cost-input=0.0, x-litellm-response-cost-output=0.0, x-litellm-response-cost-tool-usage=0.0, x-litellm-key-spend=0.0, x-litellm-response-duration-ms=4420.979022979736, x-litellm-overhead-duration-ms=3104.1882, x-litellm-callback-duration-ms=0.0, x-litellm-model-group=agent-llm, x-litellm-attempted-retries=0, x-litellm-attempted-fallbacks=0`
