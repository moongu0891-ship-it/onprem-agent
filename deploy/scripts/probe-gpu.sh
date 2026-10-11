#!/usr/bin/env bash
# 01장: minikube(docker 드라이버) 안의 Pod 가 노트북 GPU 를 볼 수 있는지 — 결과가 뒤 장의 모양을 정한다.
#   bash deploy/scripts/probe-gpu.sh          결과는 results/cloud/01_gpu_probe.txt 에도 남는다
# 되면: 모델 서버(SGLang)를 클러스터 안 Pod 로 올린다(05장). 안 되면: 모델 서버는 호스트 Docker 에 두고 클러스터는 host.minikube.internal 로 붙는다.
set -u
OUT=results/cloud; mkdir -p "$OUT"; LOG="$OUT/01_gpu_probe.txt"
{
echo "## $(date -Is)"
echo "### 호스트"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv 2>&1 | head -3
docker info 2>/dev/null | grep -i -A1 "Runtimes" | head -3
echo "### minikube"
minikube version 2>&1 | head -1
minikube status -p agent 2>&1 | head -5
echo "### Pod 에서 GPU 보이나 (nvidia-smi)"
kubectl -n lab delete pod gpu-probe --ignore-not-found >/dev/null 2>&1
kubectl -n lab run gpu-probe --restart=Never --image=nvidia/cuda:12.6.3-base-ubuntu24.04 \
  --overrides='{"spec":{"containers":[{"name":"gpu-probe","image":"nvidia/cuda:12.6.3-base-ubuntu24.04","command":["nvidia-smi","-L"],"resources":{"limits":{"nvidia.com/gpu":1}}}],"restartPolicy":"Never"}}' 2>&1
kubectl -n lab wait --for=jsonpath='{.status.phase}'=Succeeded pod/gpu-probe --timeout=180s 2>&1 || true
kubectl -n lab get pod gpu-probe -o wide 2>&1
kubectl -n lab logs gpu-probe 2>&1 | head -5
kubectl -n lab describe pod gpu-probe 2>&1 | grep -A6 "^Events" | head -8
echo "### 노드가 광고하는 GPU 수"
kubectl get node -o jsonpath='{range .items[*]}{.metadata.name}{" gpu="}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}' 2>&1
} | tee -a "$LOG"
echo; echo "저장: $LOG — 'GPU 0: NVIDIA GeForce RTX 5070 …' 한 줄이 보이면 성공"
