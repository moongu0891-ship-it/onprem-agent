# 서빙 계층

같은 모델을 vLLM · SGLang · llama.cpp 로 띄우고, 같은 요청 묶음으로 속도와 도구 호출 정확도를 비교한다.
에이전트는 엔진 주소 대신 LiteLLM 게이트웨이의 이름(`agent-llm`)만 알고, 엔진 교체나 장애 시 대체는 게이트웨이가 맡는다.

## 무엇을 재나

| 지표 | 뜻 | 왜 보나 |
|---|---|---|
| TTFT | 요청부터 첫 토큰까지 | 사용자가 "반응한다"고 느끼는 시간. 입력이 길수록(=에이전트) 커진다 |
| TPOT | 첫 토큰 뒤 토큰당 시간 | 글자가 나오는 속도. 동시 사용자가 늘면 커진다 |
| 처리량 | 초당 요청 수, 초당 출력 토큰 수 | 서버 한 대가 감당하는 양 |
| 굿풋 | 목표(첫 토큰 1초, 토큰당 50ms)를 지킨 요청만 센 처리량 | "몇 명까지 받을 수 있나"의 실제 답 |
| 캐시 재사용 | 입력 토큰 중 다시 계산하지 않은 비율 | 에이전트는 모든 요청이 같은 긴 시스템 프롬프트로 시작한다 |
| 도구 호출 정확도 | 20문항에서 맞는 도구·인자를 고른 비율 | 엔진마다 도구 호출 파서가 다르다 |

요청 모양 세 가지 (모두 이 저장소의 실제 문서·질문으로 만든다, `src/onprem_agent/serving/workloads.py`)
- **chat**: 짧은 질문 하나. 앞부분 공유가 거의 없다.
- **rag**: 에이전트 시스템 프롬프트(도구 설명 포함, 약 2,500자, 모든 요청이 같음) + 검색 문서 3개 + 질문.
- **multiturn**: rag 로 시작해 같은 대화에서 후속 질문 2개. 앞 대화 전체가 다음 요청의 앞부분이 된다.

공정하게 재려고 지킨 것
- 세 엔진 모두 같은 모델 이름·같은 최대 길이(8192)·온도 0·출력 128토큰 고정(`ignore_eos`)·Qwen3 생각 모드 끔.
- 사용자 메시지 앞에 요청마다 다른 꼬리표를 붙인다. 같은 질문이 두 번 뽑혀도 캐시를 공짜로 얻지 않게.
- 동시 사용자 단계마다 다른 요청 묶음을 쓴다. 앞 단계가 남긴 캐시가 다음 단계를 돕지 않게.
- 첫 요청 2개는 예열로 빼고 잰다.
- 캐시 효과는 같은 엔진의 '캐시 끔' 프로필(`--no-enable-prefix-caching`, `--disable-radix-cache`)과 비교한다.
- 차이: llama.cpp 는 GGUF 만 읽어서 Q8_0 양자화 모델을 쓴다. 표에 함께 적는다.

## 노트북에서 실행 (RTX 5070 Laptop 8GB)

```bash
git pull && pip install -e ".[serving]"
docker compose --profile all down          # 벡터DB 컨테이너를 내려 RAM 확보 (데이터는 남음)

# 1) 동작 확인: 엔진마다 띄우고 → 짧게 재고 → 내린다 (첫 실행은 이미지·모델 내려받기로 오래 걸림)
python scripts/bench_serving.py configs/serving_laptop.yaml --manage --quick

# 2) 본 측정
python scripts/bench_serving.py configs/serving_laptop.yaml --manage
cat results/serving_laptop.md
```

한 엔진만: `--only SGLang`. 이미 떠 있는 엔진을 재려면 `--manage` 를 빼면 된다.

문제가 생기면
- 엔진 로그: `docker compose -f serving/compose.yml --profile sglang logs --tail 50`
- SGLang 도구 호출 파서 이름이 버전에 따라 다르다: `SGLANG_TOOL_PARSER=qwen python scripts/bench_serving.py ...`
- SGLang 이 Blackwell 노트북 GPU 에서 커널 오류를 내면: `SGLANG_EXTRA="--attention-backend triton" ...`
- 이미지 버전 고정: `VLLM_IMAGE=vllm/vllm-openai:v0.x.y` 처럼 환경 변수로 바꾼다.
