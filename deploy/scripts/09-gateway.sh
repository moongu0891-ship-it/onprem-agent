#!/usr/bin/env bash
# 09장: 기본 인증 Secret → Ingress 교체 → 요청 제한·인증 측정, LiteLLM 게이트웨이 띄우고 키 검사 → results/cloud/09_gateway.txt
#   bash deploy/scripts/09-gateway.sh [사용자: agent] [비밀번호: agent-pass]
set -euo pipefail
USER_=${1:-agent}; PASS=${2:-agent-pass}; OUT=results/cloud/09_gateway.txt; mkdir -p results/cloud var
IP=$(minikube -p agent ip)
{
  echo "== $(date '+%F %T')"
  printf '%s:%s\n' "$USER_" "$(openssl passwd -apr1 "$PASS")" > var/auth
  kubectl -n lab create secret generic basic-auth --from-file=auth=var/auth --dry-run=client -o yaml | kubectl apply -f -
  kubectl apply -f deploy/manifests/09-ingress-auth.yaml
  kubectl apply -f deploy/manifests/09-litellm.yaml
  sleep 5
  echo "-- 인증: 없이 → 401, 맞는 계정 → 200"
  curl -sk -o /dev/null -w '없이  %{http_code}\n' --resolve console.local:443:$IP https://console.local/healthz
  curl -sk -o /dev/null -w '계정  %{http_code}\n' -u "$USER_:$PASS" --resolve console.local:443:$IP https://console.local/healthz
  echo "-- 요청 제한: 40 요청을 한꺼번에 → 초당 5 넘는 만큼 503"
  for i in $(seq 1 40); do curl -sk -o /dev/null -w '%{http_code}\n' -u "$USER_:$PASS" --resolve console.local:443:$IP https://console.local/healthz & done | sort | uniq -c
  echo "-- LiteLLM 게이트웨이"
  kubectl -n lab rollout status deploy/litellm --timeout=300s
  KEY=$(kubectl -n lab get secret model-keys -o jsonpath='{.data.gateway}' | base64 -d)
  kubectl -n lab delete pod gw-probe --ignore-not-found --wait=true >/dev/null
  kubectl -n lab run gw-probe --image=curlimages/curl:8.10.1 --restart=Never --quiet -- sh -c "
    curl -s -o /dev/null -w '틀린 키 → %{http_code}\n' -H 'Authorization: Bearer wrong' http://litellm.lab:4000/v1/models
    curl -s -o /dev/null -w '맞는 키 → %{http_code}\n' -H 'Authorization: Bearer $KEY' http://litellm.lab:4000/v1/models
    curl -s -m 120 -H 'Authorization: Bearer $KEY' -H 'Content-Type: application/json' http://litellm.lab:4000/v1/chat/completions \
      -d '{\"model\":\"agent-llm-4b\",\"messages\":[{\"role\":\"user\",\"content\":\"한 단어로 답해: 하늘 색은?\"}],\"max_tokens\":64,\"chat_template_kwargs\":{\"enable_thinking\":false}}' | cut -c1-300; echo"
  kubectl -n lab wait --for=jsonpath='{.status.phase}'=Succeeded pod/gw-probe --timeout=180s >/dev/null 2>&1 || true
  kubectl -n lab logs gw-probe; kubectl -n lab delete pod gw-probe --wait=false >/dev/null
} 2>&1 | tee -a "$OUT"
