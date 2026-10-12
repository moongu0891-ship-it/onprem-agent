#!/usr/bin/env bash
# 12장: 전체 시험 전후로 클러스터의 무거운 것을 내리고(down) 올린다(up). 밤 시험은 노트북 GPU 를 혼자 써야 한다.
#   bash deploy/scripts/12-quiet.sh down|up
set -euo pipefail
case "${1:-}" in
  down) kubectl -n lab scale deploy/sglang deploy/console deploy/litellm --replicas=0 2>/dev/null || true
        kubectl -n lab wait --for=delete pod -l app=sglang --timeout=120s 2>/dev/null || true
        echo "내림: sglang · console · litellm (GPU 비움)";;
  up)   kubectl -n lab scale deploy/sglang deploy/console deploy/litellm --replicas=1 2>/dev/null || true
        echo "올림: sglang · console · litellm";;
  *) echo "사용법: $0 down|up"; exit 2;;
esac
