#!/usr/bin/env bash
# 04장: 창구 정의(ConfigMap)와 모델 키(Secret)를 만든다. 다시 돌려도 된다(apply).
#   bash deploy/scripts/04-config.sh [examples/desks/it/desk.yaml]
set -euo pipefail
DESK=${1:-examples/desks/it/desk.yaml}
kubectl -n lab create configmap desk-it --from-file=desk.yaml="$DESK" --dry-run=client -o yaml | kubectl apply -f -
# 키 값은 Git 에 두지 않는다 — 환경 변수 GATEWAY_KEY 가 있으면 그것, 없으면 5주차 개발용 키
kubectl -n lab create secret generic model-keys --from-literal=gateway="${GATEWAY_KEY:-sk-local-dev}" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n lab get configmap desk-it secret model-keys
