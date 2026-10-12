#!/usr/bin/env bash
# 05장: 클러스터 안에서 Service 로 N 번 부르고 어느 Pod 가 답했는지 센다 → results/cloud/05_lb.txt
#   bash deploy/scripts/05-lb.sh [횟수: 30]
# port-forward 는 Pod 하나에 고정되므로 쓰지 않는다 — 클러스터 안에서 curl Pod 를 띄워 Service 이름으로 부른다.
# 줄마다 'HTTP코드 Pod이름'. 출력은 Pod 가 끝난 뒤 logs 로 읽는다 — `kubectl run -i` 는 붙기 전에 찍힌 앞 몇 줄을 잃는다(D45: 30회 중 3~4회가 비어 보였다).
set -euo pipefail
N=${1:-30}; OUT=results/cloud/05_lb.txt; mkdir -p results/cloud
{
  echo "== $(date '+%F %T')  replicas=$(kubectl -n lab get deploy console -o jsonpath='{.status.readyReplicas}')  요청 $N 회"
  kubectl -n lab delete pod lb-probe --ignore-not-found --wait=true >/dev/null
  kubectl -n lab run lb-probe --image=curlimages/curl:8.10.1 --restart=Never --quiet -- \
    sh -c "for i in \$(seq 1 $N); do curl -s -o /dev/null -w '%{http_code} %header{X-Served-By}\n' http://console.lab/healthz; done"
  kubectl -n lab wait --for=jsonpath='{.status.phase}'=Succeeded pod/lb-probe --timeout=120s >/dev/null
  kubectl -n lab logs lb-probe | sort | uniq -c
  echo "합계: $(kubectl -n lab logs lb-probe | wc -l) 줄"
  kubectl -n lab delete pod lb-probe --wait=false >/dev/null
} 2>&1 | tee -a "$OUT"
