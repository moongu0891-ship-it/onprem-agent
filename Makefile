# 시험 세 단계 + 빨간불 (7주차 ②, docs/재는_방법.md 4절). CI 도구에 묶이지 않게 명령만 둔다 — GitHub Actions·Jenkins 가 같은 명령을 부른다.
#
#   make test-unit                      단위: 함수 하나씩(채점 규칙·글로 쓴 호출 해석·근거 붙이기·빨간불 판정…), 수십 초, GPU 없음
#   make test-module                    모듈: 업무 기능(도구) 서버 + 그래프 + 채점기를 규칙 모델로, 몇 분, GPU 없음
#   make test-full CONFIG=configs/…     전체: 실제 모델로 같은 설정 두 번 + 빨간불 검사, 약 1시간, 노트북 GPU
#       BASE=바탕                        같은 설정 안의 바탕 시험 조건(이름에 든 글자)과 견줌
#       REF=results/reference           또는 예전에 받아들인 결과(같은 이름의 시험 조건)와 견줌 — 매일 밤
#   make accept CONFIG=configs/…        방금 test-full 결과를 '받아들인 결과'로 둔다(사람이 실제 답을 읽은 뒤에만)
#   make check-docs                     문서 링크·앵커 검사
#   make web [MODEL=sglang-4b]          웹 화면 (상담 / · 관리자 /admin)

PY ?= python3
CONFIG ?=
BASE ?=
REF ?=
NAME = $(shell $(PY) -c "import yaml; print(yaml.safe_load(open('$(CONFIG)', encoding='utf-8'))['name'])")

.PHONY: test-unit test-module test-full accept check-docs test web cloud-up cloud-down cloud-destroy

test-unit:
	$(PY) -m pytest -q -m "not module"

test-module:
	$(PY) -m pytest -q -m module
	$(PY) scripts/eval_agent.py configs/agent_ci.yaml
	$(PY) scripts/eval_agent.py configs/agent_ci_guard.yaml
	$(PY) scripts/eval_agent.py configs/agent_ci_default.yaml
	$(PY) scripts/gate.py results/agent_ci.json
	$(PY) scripts/gate.py results/agent_ci_guard.json
	$(PY) scripts/gate.py results/agent_ci_default.json --expect tests/expected/agent_ci_default.json

test-full:
	@test -n "$(CONFIG)" || { echo "CONFIG=configs/… 를 주세요"; exit 2; }
	$(PY) scripts/eval_agent.py $(CONFIG) --manage --run-tag r1
	$(PY) scripts/eval_agent.py $(CONFIG) --manage --run-tag r2
	$(PY) scripts/gate.py results/$(NAME)_r1.json results/$(NAME)_r2.json \
		$(if $(BASE),--baseline "$(BASE)") \
		$(if $(REF),--reference $(wildcard $(REF)/$(NAME)_r*.json))

accept:
	@test -n "$(CONFIG)" || { echo "CONFIG=configs/… 를 주세요"; exit 2; }
	mkdir -p results/reference
	cp results/$(NAME)_r1.json results/$(NAME)_r2.json results/reference/

check-docs:
	$(PY) scripts/check_links.py

test: test-unit test-module check-docs

web:                                    ## 웹 화면 (MODEL=sglang-4b 처럼 바꿀 수 있다)
	$(PY) scripts/web.py --model $(or $(MODEL),rule)

cloud-up:                               ## 8주차 13장: minikube 위에 전부 올린다(01~11장 순서, 멱등). 처음부터면 20~40분
	bash deploy/scripts/cloud-up.sh

cloud-down:                             ## 클러스터를 멈춘다(내용은 남는다). 다시: make cloud-up
	minikube -p agent stop

cloud-destroy:                          ## 클러스터를 지운다(이미지·PVC·DB 전부). 처음부터 다시 재려면
	minikube -p agent delete
