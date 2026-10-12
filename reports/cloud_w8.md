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

`port-forward 8080:80` 은 `address already in use` 로 실패(8080 을 다른 프로그램이 씀) → `18080:80` 으로 열어 브라우저에서 확인(연결 6건).

04-002 (설정만 바꾸기):
```
configmap/desk-it configured
deployment.apps/console restarted … successfully rolled out
"placeholder": "(ConfigMap 에서 바꾼 문구) 무엇이든 물어보세요"     ← IT 창구(세 창구 중 셋째)
configmap/desk-it configured                                    ← 되돌림
```
(`python3 -m json.tool` 이 한글을 `\uXXXX` 로 찍었는데 풀면 위 문구. `NotFound` 두 줄은 `04-config.sh` 의 확인 명령 오류로, d23e093 에서 고침 — 만들기는 성공)

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

## 06장 HPA (2026-10-12)

```
== 2026-10-12 09:23:17  replicas=1  요청 30 회
     26 200 console-6497f8dcd-xjtrp          ← 4회 빠짐: 측정기(D45)
== 2026-10-12 09:23:19  부하 150초 · 동시 8  (HPA: 1-4, cpu 50%)
시각      HPA(현재/목표 %)   Pod 수  준비된 Pod
09:23:20  /50                1  1
09:23:40  2/50               1  1
09:24:11  2/50               1  1
09:24:21  315/50             3  2
09:24:32  315/50             4  3
09:24:42  315/50             4  4
09:25:23  194/50             4  4
09:26:25  115/50             4  4
09:27:16  115/50             4  4      ← 관찰 끝(부하는 09:25:49 에 끝남)
-- 부하 Pod 출력: 요청 9376 개
console-…-2rjn5   4m   680Mi
console-…-lvgfg   4m   676Mi
console-…-wtrqb   4m   670Mi
console-…-xjtrp   4m   764Mi
Events: FailedGetResourceMetric(처음 1분, metrics-server 가 아직) → SuccessfulRescale 3 → 4
```
