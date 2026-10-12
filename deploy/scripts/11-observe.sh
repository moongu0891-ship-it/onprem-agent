#!/usr/bin/env bash
# 11장: Prometheus + Grafana 를 helm 으로 올리고, 부하를 건 뒤 Prometheus API 로 p95·초당 질문 수를 읽는다 → results/cloud/11_observe.txt
#   bash deploy/scripts/11-observe.sh [부하 초: 60] [동시: 4]
set -euo pipefail
SECS=${1:-60}; PAR=${2:-4}; OUT=results/cloud/11_observe.txt; mkdir -p results/cloud
{
  echo "== $(date '+%F %T')"
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
  helm repo add grafana https://grafana.github.io/helm-charts >/dev/null 2>&1 || true
  helm repo update >/dev/null
  kubectl apply -f deploy/manifests/11-dashboard.yaml
  helm upgrade --install prometheus prometheus-community/prometheus -n lab -f deploy/helm/prometheus-values.yaml --wait --timeout 300s
  helm upgrade --install grafana grafana/grafana -n lab -f deploy/helm/grafana-values.yaml --wait --timeout 300s
  # 스크레이프 주석만 더한다(apply 로 04 매니페스트를 다시 넣으면 10장의 env·이미지가 되돌아가므로 patch)
  kubectl -n lab patch deploy console -p '{"spec":{"template":{"metadata":{"annotations":{"prometheus.io/scrape":"true","prometheus.io/port":"8080","prometheus.io/path":"/metrics"}}}}}' >/dev/null
  kubectl -n lab set image deploy/console console=onprem-agent:v3 >/dev/null   # /metrics 가 든 이미지(bash deploy/scripts/03-build.sh v3)
  kubectl -n lab rollout status deploy/console --timeout=300s
  echo "-- Prometheus 가 상담 화면을 긁나"
  kubectl -n lab port-forward svc/prometheus-server 9090:80 >/dev/null 2>&1 & PF=$!; sleep 3
  curl -s 'http://127.0.0.1:9090/api/v1/targets' | python3 -c "import sys,json; t=[x for x in json.load(sys.stdin)['data']['activeTargets'] if 'console' in json.dumps(x)]; print('console 대상', len(t), [x['health'] for x in t])"
  echo "-- 부하 ${SECS}초 · 동시 $PAR (규칙 모델이면 빠르고, 실제 모델이면 느리다 — 어느 쪽인지 적는다: $(kubectl -n lab get deploy console -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="ONPREM_MODEL")].value}'))"
  kubectl -n lab delete pod load --ignore-not-found --wait=false >/dev/null
  kubectl -n lab run load --image=curlimages/curl:8.10.1 --restart=Never --quiet -- sh -c "
    end=\$((\$(date +%s)+$SECS)); while [ \$(date +%s) -lt \$end ]; do
      for i in \$(seq 1 $PAR); do curl -s -m 120 -o /dev/null -X POST http://console.lab/api/chat -H 'Content-Type: application/json' \
        -d '{\"desk\":\"it\",\"question\":\"VPN-809 오류가 떠요. 어떻게 해야 해요?\"}' & done; wait; done" >/dev/null
  sleep $((SECS + 30))
  q() { curl -s --data-urlencode "query=$1" 'http://127.0.0.1:9090/api/v1/query' | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(' · '.join(f\"{x['metric'].get('pod','')} {float(x['value'][1]):.3f}\" for x in r) or '없음')"; }
  echo "초당 질문 수(1분 평균, Pod 별): $(q 'sum by (pod) (rate(agent_chat_total[1m]))')"
  echo "처리 시간 p95(초):            $(q 'histogram_quantile(0.95, sum by (le) (rate(agent_turn_seconds_bucket[5m])))')"
  echo "질문 누적:                    $(q 'sum(agent_chat_total)')"
  echo "확인 대기 / 오류 누적:        $(q 'sum(agent_chat_status_total{status=\"확인 대기\"})') / $(q 'sum(agent_chat_status_total{status=\"오류\"})')"
  kill $PF; kubectl -n lab delete pod load --ignore-not-found --wait=false >/dev/null
  echo "Grafana: kubectl -n lab port-forward svc/grafana 3000:80 → http://127.0.0.1:3000 (admin / lab-admin) → 대시보드 '사내 AI 상담 — 운영'"
} 2>&1 | tee -a "$OUT"
