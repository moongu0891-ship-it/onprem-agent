#!/usr/bin/env bash
# 13장: 한 줄로 전부 — 01~11장을 순서대로, 다시 돌려도 되게(멱등). 처음부터 걸리는 시간을 results/cloud/13_cloud_up.txt 에 남긴다.
#   make cloud-up            (= bash deploy/scripts/cloud-up.sh)
#   SKIP_JENKINS=1 이면 12장 건너뜀(기본 건너뜀 — 일꾼 접속은 사람이 붙여야 해서). WITH_JENKINS=1 로 포함.
set -euo pipefail
OUT=results/cloud/13_cloud_up.txt; mkdir -p results/cloud
T0=$(date +%s); step() { echo "[$(( $(date +%s)-T0 ))s] $*"; }
{
  echo "== $(date '+%F %T')  commit $(git rev-parse --short HEAD)"
  step "01 클러스터"
  minikube -p agent status >/dev/null 2>&1 || minikube start -p agent --driver=docker --container-runtime=docker --gpus=all --memory=6g --cpus=4
  minikube -p agent status | grep -q "host: Running" || minikube -p agent start
  docker update --memory=12g --memory-swap=12g agent >/dev/null       # 07장 측정으로 정한 노드 상한
  kubectl get ns lab >/dev/null 2>&1 || kubectl create namespace lab
  minikube -p agent addons enable nvidia-device-plugin >/dev/null; minikube -p agent addons enable metrics-server >/dev/null; minikube -p agent addons enable ingress >/dev/null
  for i in $(seq 1 30); do kubectl -n lab get sa default >/dev/null 2>&1 && break; sleep 1; done
  step "03 이미지 v3"
  minikube -p agent image ls | grep -q onprem-agent:v3 || bash deploy/scripts/03-build.sh v3 >/dev/null
  step "04 설정·상담 화면"
  bash deploy/scripts/04-config.sh >/dev/null
  kubectl apply -f deploy/manifests/04-console.yaml >/dev/null
  kubectl -n lab set image deploy/console console=onprem-agent:v3 >/dev/null
  step "07 모델 서버"
  kubectl apply -f deploy/manifests/07-sglang.yaml >/dev/null
  kubectl -n lab get job download-qwen3-4b >/dev/null 2>&1 || kubectl apply -f deploy/manifests/07-download.yaml >/dev/null
  kubectl -n lab wait --for=condition=complete job/download-qwen3-4b --timeout=1800s >/dev/null 2>&1 || true
  step "10 DB·색인"
  kubectl apply -f deploy/manifests/10-postgres.yaml >/dev/null
  kubectl -n lab rollout status sts/postgres --timeout=300s >/dev/null
  kubectl -n lab get job index-corpus >/dev/null 2>&1 || kubectl apply -f deploy/manifests/10-postgres.yaml >/dev/null
  kubectl -n lab set env deploy/console ONPREM_WEB_STORE=postgres ONPREM_PG_DSN=postgresql://agent:agent@postgres:5432/agent \
      ONPREM_STORE='{"kind":"pgvector","dsn":"postgresql://agent:agent@postgres:5432/agent"}' ONPREM_INDEX=reuse >/dev/null
  step "08·09 엣지·관문"
  kubectl -n ingress-nginx rollout status deploy/ingress-nginx-controller --timeout=300s >/dev/null
  [ -f var/console.key ] || openssl req -x509 -nodes -newkey rsa:2048 -days 365 -subj "/CN=console.local" -keyout var/console.key -out var/console.crt >/dev/null 2>&1
  kubectl -n lab create secret tls console-tls --key var/console.key --cert var/console.crt --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  [ -f var/auth ] || printf 'agent:%s\n' "$(openssl passwd -apr1 agent-pass)" > var/auth
  kubectl -n lab create secret generic basic-auth --from-file=auth=var/auth --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  for i in $(seq 1 12); do kubectl apply -f deploy/manifests/09-ingress-auth.yaml >/dev/null 2>&1 && break; sleep 5; done
  kubectl apply -f deploy/manifests/09-litellm.yaml >/dev/null
  kubectl -n lab set env deploy/console ONPREM_MODEL=gateway ONPREM_MODEL_URL=http://litellm:4000/v1 >/dev/null
  step "11 관측"
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
  helm repo add grafana https://grafana.github.io/helm-charts >/dev/null 2>&1 || true
  kubectl apply -f deploy/manifests/11-dashboard.yaml >/dev/null
  helm upgrade --install prometheus prometheus-community/prometheus -n lab -f deploy/helm/prometheus-values.yaml >/dev/null
  helm upgrade --install grafana grafana/grafana -n lab -f deploy/helm/grafana-values.yaml >/dev/null
  kubectl -n lab patch deploy console -p '{"spec":{"template":{"metadata":{"annotations":{"prometheus.io/scrape":"true","prometheus.io/port":"8080","prometheus.io/path":"/metrics"}}}}}' >/dev/null
  if [ "${WITH_JENKINS:-0}" = "1" ]; then step "12 Jenkins"; bash deploy/scripts/12-jenkins.sh >/dev/null; fi
  step "기다림: 모델 서버 → 게이트웨이 → 상담 화면"
  kubectl -n lab rollout status deploy/sglang --timeout=1800s >/dev/null
  kubectl -n lab rollout status deploy/litellm --timeout=600s >/dev/null
  kubectl -n lab rollout status deploy/console --timeout=600s >/dev/null
  step "확인: https://console.local/healthz"
  curl -sk -o /dev/null -w 'https %{http_code}  Pod %header{X-Served-By}\n' -u agent:agent-pass --resolve console.local:443:$(minikube -p agent ip) https://console.local/healthz
  kubectl -n lab get pods
  step "끝 — 전체 $(( ($(date +%s)-T0)/60 ))분"
} 2>&1 | tee -a "$OUT"
