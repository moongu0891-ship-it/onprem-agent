#!/usr/bin/env bash
# 05장: 승인을 기다리는 상담 중에 그 Pod 를 죽이고, 같은 상담 번호로 승인이 이어지는지 본다 → results/cloud/05_kill.txt
#   bash deploy/scripts/05-kill.sh
# 화면 대신 API 로 한다: /api/chat 은 SSE 로 사건을 흘려 보내며, 담당자 확인이 필요하면 approval 사건 뒤 멈춘다.
set -euo pipefail
OUT=results/cloud/05_kill.txt; mkdir -p results/cloud
Q='E1063 계정 잠금 해제 요청해 줘. 비밀번호를 다섯 번 틀렸대요. 본인 확인은 끝났어요.'
{
  echo "== $(date '+%F %T')  replicas=$(kubectl -n lab get deploy console -o jsonpath='{.status.readyReplicas}')"
  kubectl -n lab run kill-probe --image=curlimages/curl:8.10.1 --restart=Never --rm -i --quiet -- sh -c '
    T=t-kill-$(date +%s)
    echo "상담 번호 $T"
    curl -s -N -m 60 -D /tmp/h -X POST http://console.lab/api/chat -H "Content-Type: application/json" \
      -d "{\"desk\":\"it\",\"thread\":\"$T\",\"question\":\"'"$Q"'\"}" | grep -m1 -E "approval|answer" | cut -c1-160
    echo "답한 Pod: $(grep -i x-served-by /tmp/h)"
    echo "$T" > /tmp/t; cat /tmp/t
  ' | tee /tmp/kill-probe.txt
  T=$(grep -o 't-kill-[0-9]*' /tmp/kill-probe.txt | head -1); POD=$(grep -io 'console-[a-z0-9-]*' /tmp/kill-probe.txt | head -1)
  echo "-- 그 Pod($POD)를 지운다"; kubectl -n lab delete pod "$POD" --wait=false
  sleep 3
  echo "-- 같은 상담 번호($T)로 승인을 보낸다(다른 Pod 가 받는다)"
  kubectl -n lab run kill-probe2 --image=curlimages/curl:8.10.1 --restart=Never --rm -i --quiet -- sh -c "
    curl -s -m 60 -w '\nHTTP %{http_code}  Pod %header{X-Served-By}\n' -X POST http://console.lab/api/approve \
      -H 'Content-Type: application/json' -d '{\"desk\":\"it\",\"thread\":\"$T\",\"approved\":true}' | cut -c1-300"
} 2>&1 | tee -a "$OUT"
