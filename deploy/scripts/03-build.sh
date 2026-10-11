#!/usr/bin/env bash
# 03장: 에이전트 이미지를 만들어 minikube 노드에 넣고, 크기·시간을 results/cloud/03_image.txt 에 남긴다.
#   bash deploy/scripts/03-build.sh [태그: v1]
set -euo pipefail
TAG=${1:-v1}; IMG=onprem-agent:$TAG; OUT=results/cloud/03_image.txt; mkdir -p results/cloud
{
  echo "== $(date '+%F %T')  $IMG  commit $(git rev-parse --short HEAD)"
  t0=$(date +%s); docker build -q -f deploy/Dockerfile -t "$IMG" . ; t1=$(date +%s)
  echo "build: $((t1-t0))s"
  docker image inspect "$IMG" --format 'size: {{.Size}} bytes  layers: {{len .RootFS.Layers}}'
  docker history "$IMG" --format '{{.Size}}\t{{.CreatedBy}}' | head -14
  echo "-- run check (host docker): /healthz"
  docker run -d --rm --name agent-check -p 18080:8080 "$IMG" >/dev/null
  for i in $(seq 1 30); do curl -sf http://127.0.0.1:18080/healthz && break || sleep 1; done; echo
  docker stop agent-check >/dev/null
  t2=$(date +%s); minikube -p agent image load "$IMG"; t3=$(date +%s)
  echo "load into minikube: $((t3-t2))s"
  minikube -p agent image ls | grep onprem-agent
} 2>&1 | tee "$OUT"
