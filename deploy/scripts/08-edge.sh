#!/usr/bin/env bash
# 08장: 자체 서명 인증서 → Secret, Ingress·NetworkPolicy 적용, 그리고 잰다 → results/cloud/08_edge.txt
#   bash deploy/scripts/08-edge.sh
# 전제: minikube -p agent addons enable ingress (워크북 08-001 1행). minikube 의 NetworkPolicy 는 CNI 가 있어야 동작한다 — 01장에서
# 기본 CNI(kindnet) 는 NetworkPolicy 를 강제하지 않으므로, 막히는지 여부 자체가 이 장의 측정 결과다(실제 클라우드의 CNI 는 강제한다).
set -euo pipefail
OUT=results/cloud/08_edge.txt; mkdir -p results/cloud var
IP=$(minikube -p agent ip)
{
  echo "== $(date '+%F %T')  minikube ip $IP"
  [ -f var/console.key ] || openssl req -x509 -nodes -newkey rsa:2048 -days 365 -subj "/CN=console.local" \
      -keyout var/console.key -out var/console.crt >/dev/null 2>&1
  kubectl -n lab create secret tls console-tls --key var/console.key --cert var/console.crt --dry-run=client -o yaml | kubectl apply -f -
  kubectl -n ingress-nginx rollout status deploy/ingress-nginx-controller --timeout=180s   # 검증 웹훅이 뜬 뒤에 Ingress 를 넣는다(안 그러면 connection refused)
  for i in $(seq 1 12); do kubectl apply -f deploy/manifests/08-ingress.yaml && break; echo "웹훅 준비 기다림 ($i)"; sleep 5; done
  sleep 5
  echo "-- http → https 되돌림 (308 이어야 한다)"
  curl -s -o /dev/null -w 'http  %{http_code} → %{redirect_url}\n' --resolve console.local:80:$IP  http://console.local/healthz
  echo "-- https (자체 서명이라 -k, 200 이어야 한다)"
  curl -sk -o /dev/null -w 'https %{http_code}  서버 %header{X-Served-By}\n' --resolve console.local:443:$IP https://console.local/healthz
  echo "-- 인증서"
  echo | openssl s_client -connect $IP:443 -servername console.local 2>/dev/null | openssl x509 -noout -subject -dates
  echo "-- CDN 흉내: 정적 파일 두 번 — 두 번째는 ETag 로 304, Cache-Control 머리말"
  curl -sk -D - -o /dev/null --resolve console.local:443:$IP https://console.local/static/app.css | grep -iE "^HTTP|etag|cache-control" | tr -d '\r'
  ET=$(curl -sk -D - -o /dev/null --resolve console.local:443:$IP https://console.local/static/app.css | grep -i '^etag' | cut -d' ' -f2 | tr -d '\r')
  curl -sk -o /dev/null -w '두 번째(If-None-Match): %{http_code}\n' -H "If-None-Match: $ET" --resolve console.local:443:$IP https://console.local/static/app.css
  echo "-- NetworkPolicy: 라벨 없는 Pod 에서 모델 서버로 (막히면 timeout=28 / 000, 안 막히면 200)"
  kubectl -n lab delete pod np-probe --ignore-not-found --wait=true >/dev/null
  kubectl -n lab run np-probe --image=curlimages/curl:8.10.1 --restart=Never --quiet -- \
    sh -c 'curl -s -m 5 -o /dev/null -w "라벨 없음 → sglang: %{http_code} (exit %{exitcode})\n" http://sglang.lab:30000/health'
  kubectl -n lab wait --for=jsonpath='{.status.phase}'=Succeeded pod/np-probe --timeout=60s >/dev/null 2>&1 || true
  kubectl -n lab logs np-probe; kubectl -n lab delete pod np-probe --wait=false >/dev/null
  echo "-- 같은 요청을 상담 화면 Pod 에서 (허용 → 200)"
  kubectl -n lab exec deploy/console -- python -c "import urllib.request as u;print('console → sglang:', u.urlopen('http://sglang:30000/health', timeout=5).status)" 2>&1 | tail -1
} 2>&1 | tee -a "$OUT"
