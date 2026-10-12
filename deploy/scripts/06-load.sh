#!/usr/bin/env bash
# 06장: 상담 화면에 부하를 걸고 HPA 가 Pod 를 늘리는 과정을 10초마다 적는다 → results/cloud/06_hpa.txt
#   bash deploy/scripts/06-load.sh [부하 초: 150] [동시 요청: 8] [부하 뒤 더 볼 초: 240]
# 부하 뒤 240초를 보는 이유: 지표가 약 60초 늦게 오고 줄이기는 60초 안정 창 뒤라, 첫 측정(90초)에서는 줄어드는 것을 못 봤다.
# 부하 Pod 는 클러스터 안에서 /api/chat 에 규칙 모델 질문을 동시에 계속 보낸다(실제 상담과 같은 경로: 그래프 + 창구 서버).
set -euo pipefail
SECS=${1:-150}; PAR=${2:-8}; TAIL=${3:-240}; OUT=results/cloud/06_hpa.txt; mkdir -p results/cloud
Q='VPN-809 오류가 떠요. 어떻게 해야 해요?'
kubectl -n lab delete pod load --ignore-not-found --wait=false >/dev/null
{
  echo "== $(date '+%F %T')  부하 ${SECS}초 · 동시 $PAR  (HPA: $(kubectl -n lab get hpa console -o jsonpath='{.spec.minReplicas}-{.spec.maxReplicas}, cpu {.spec.metrics[0].resource.target.averageUtilization}%'))"
  kubectl -n lab run load --image=curlimages/curl:8.10.1 --restart=Never --quiet -- sh -c "
    end=\$((\$(date +%s)+$SECS)); n=0
    while [ \$(date +%s) -lt \$end ]; do
      for i in \$(seq 1 $PAR); do
        curl -s -m 30 -o /dev/null -X POST http://console.lab/api/chat -H 'Content-Type: application/json' \
          -d '{\"desk\":\"it\",\"question\":\"$Q\"}' &
      done; wait; n=\$((n+$PAR))
    done; echo \"요청 \$n 개\"" >/dev/null
  printf '%-9s %-28s %-8s %s\n' "시각" "HPA(현재/목표 %)" "Pod 수" "준비된 Pod"
  for i in $(seq 1 $(( (SECS + TAIL) / 10 ))); do
    printf '%-9s %-28s %-8s %s\n' "$(date +%T)" \
      "$(kubectl -n lab get hpa console -o jsonpath='{.status.currentMetrics[0].resource.current.averageUtilization}/{.spec.metrics[0].resource.target.averageUtilization}')" \
      "$(kubectl -n lab get deploy console -o jsonpath='{.spec.replicas}')" \
      "$(kubectl -n lab get deploy console -o jsonpath='{.status.readyReplicas}')"
    sleep 10
  done
  echo "-- 부하 Pod 출력: $(kubectl -n lab logs load 2>/dev/null | tail -1)"
  kubectl -n lab top pod -l app=console 2>&1
  kubectl -n lab describe hpa console | sed -n '/^Events/,$p' | head -12
  kubectl -n lab delete pod load --ignore-not-found --wait=false >/dev/null
} 2>&1 | tee -a "$OUT"
