#!/usr/bin/env bash
# 00장: minikube · kubectl · helm 설치 (WSL2 Ubuntu, Docker 는 이미 있음). 한 줄씩 해설은 docs/클라우드_실습_워크북.md 00장.
set -eu
ARCH=amd64
command -v kubectl >/dev/null || { curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/$ARCH/kubectl"; sudo install -m 0755 kubectl /usr/local/bin/kubectl; rm kubectl; }
command -v minikube >/dev/null || { curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-$ARCH; sudo install minikube-linux-$ARCH /usr/local/bin/minikube; rm minikube-linux-$ARCH; }
command -v helm >/dev/null || { curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash; }
kubectl version --client; minikube version; helm version
