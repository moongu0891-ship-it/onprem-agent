#!/usr/bin/env bash
# 10장: PostgreSQL 올리기 → 색인 Job → 상담 화면을 공용 DB 로 전환 → 05장의 Pod 죽이기 다시 → results/cloud/10_db.txt
#   bash deploy/scripts/10-db.sh
set -euo pipefail
OUT=results/cloud/10_db.txt; mkdir -p results/cloud
{
  echo "== $(date '+%F %T')"
  kubectl apply -f deploy/manifests/10-postgres.yaml
  kubectl -n lab rollout status sts/postgres --timeout=300s
  echo "-- 색인 Job"
  t0=$(date +%s); kubectl -n lab wait --for=condition=complete job/index-corpus --timeout=600s; echo "Job $(( $(date +%s)-t0 ))초"
  kubectl -n lab logs job/index-corpus | tail -4
  kubectl -n lab exec sts/postgres -- psql -U agent -d agent -c "\dt" -c "SELECT count(*) FROM chunks_it;" 2>&1 | tail -8
  echo "-- 상담 화면: 새 이미지(v2), 대화 저장 postgres, 색인 재사용"
  kubectl -n lab set image deploy/console console=onprem-agent:v2
  kubectl -n lab set env deploy/console ONPREM_WEB_STORE=postgres ONPREM_PG_DSN=postgresql://agent:agent@postgres:5432/agent \
      ONPREM_STORE='{"kind":"pgvector","dsn":"postgresql://agent:agent@postgres:5432/agent"}' ONPREM_INDEX=reuse
  kubectl -n lab rollout status deploy/console --timeout=300s
  kubectl -n lab scale deploy/console --replicas=3 && kubectl -n lab rollout status deploy/console --timeout=300s
  echo "-- 05장 다시: 승인 대기 중 Pod 삭제 → 같은 상담 번호 승인 (이번엔 200 이어야 한다)"
  bash deploy/scripts/05-kill.sh
  echo "-- DB 에 남은 체크포인트"
  kubectl -n lab exec sts/postgres -- psql -U agent -d agent -c "SELECT count(*) AS checkpoints, count(DISTINCT thread_id) AS threads FROM checkpoints;" 2>&1 | tail -4
  echo "-- DB Pod 를 죽여도 데이터가 남나"
  kubectl -n lab delete pod postgres-0 --wait=true; kubectl -n lab rollout status sts/postgres --timeout=300s
  kubectl -n lab exec sts/postgres -- psql -U agent -d agent -c "SELECT count(*) FROM checkpoints;" -c "SELECT count(*) FROM chunks_it;" 2>&1 | grep -E "^ +[0-9]"
  kubectl -n lab scale deploy/console --replicas=1
} 2>&1 | tee -a "$OUT"
