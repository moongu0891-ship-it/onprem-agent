# 8주차 측정 원본 — minikube 위의 에이전트

측정 장소: 노트북(Windows 11 · WSL2 Ubuntu · Docker · minikube v1.39.0 docker 드라이버 · RTX 5070 Laptop 8GB). 해석은 [docs/클라우드_실습_워크북.md](../docs/클라우드_실습_워크북.md). 터미널 프롬프트는 지웠다.

## 01장 GPU 판정 (2026-10-12)

`results/cloud/01_gpu_probe.txt` 요약: 장치 플러그인 `k8s-device-plugin:v0.20.0` 등록, 노드 `gpu=1`, Pod 의 `nvidia-smi -L` → `GPU 0: NVIDIA GeForce RTX 5070 Laptop GPU`. 첫 실행은 `serviceaccount "default" not found` 로 거부(C9), 스크립트를 고쳐 재실행.

## 03장 이미지 (2026-10-12, 커밋 446d794)

```
== 2026-10-12 08:59:52  onprem-agent:v1  commit 446d794
build: 43s
size: 207701952 bytes  layers: 17
1.85MB  RUN /bin/sh -c mkdir -p /app/var /app/result…
12.3kB  COPY Makefile ./
111kB   COPY tests ./tests
119kB   COPY configs ./configs
73.7kB  COPY eval ./eval
815kB   COPY data ./data
160kB   COPY examples ./examples
152kB   COPY scripts ./scripts
383MB   RUN /bin/sh -c pip install -e ".[agent,web,d…
385kB   COPY src ./src
-- run check (host docker): /healthz
{"ok":true,"pod":"da212bfccd4a","model":"rule"}
load into minikube: 11s
== 2026-10-12 09:00:49  (코드 그대로 다시)
build: 1s   …   load into minikube: 6s
```

## 04장 상담 화면 Pod (2026-10-12)

```
configmap/desk-it created
secret/model-keys created
deployment.apps/console created
service/console created
deployment "console" successfully rolled out
real    0m5.860s
```

`port-forward 8080:80` 은 `address already in use` 로 실패(8080 을 다른 프로그램이 씀) — 화면 확인과 04-002 는 다음에.

## 05장 나눠 주기 · Pod 죽이기 (2026-10-12)

```
== 2026-10-12 09:01:06  replicas=3  요청 30 회
      9 console-56c555f8-f77qv
      8 console-56c555f8-nhzqj
     10 console-56c555f8-nzsdm
== 2026-10-12 09:01:13  replicas=3
상담 번호 t-kill-1791763274
data: {"type": "approval", "title": "계정 잠금 해제를 요청하려고 합니다", "button": "승인하고 요청", …
답한 Pod: x-served-by: console-56c555f8-f77qv
-- 그 Pod(console-56c555f8-f77qv)를 지운다
pod "console-56c555f8-f77qv" deleted from lab namespace
-- 같은 상담 번호(t-kill-1791763274)로 승인을 보낸다(다른 Pod 가 받는다)
{"detail":"확인을 기다리는 일이 없다"}
HTTP 409  Pod console-56c555f8-4xtcm
```

30회 중 27회만 Pod 이름이 찍혔다 — 측정기가 HTTP 코드를 안 남겨 원인을 못 가림. `05-lb.sh` 가 코드를 함께 찍게 고쳤다(다음 측정부터).
