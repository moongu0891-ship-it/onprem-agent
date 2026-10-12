# deploy/ — minikube 위에 에이전트 올리기 (8주차 워크북의 재료)

읽는 순서는 [docs/클라우드_실습_워크북.md](../docs/클라우드_실습_워크북.md). 여기 파일은 그 워크북의 장 번호를 따른다.

- `scripts/install-minikube.sh` — 00장: kubectl · minikube · helm 설치
- `scripts/probe-gpu.sh` — 01장: Pod 에서 GPU 가 보이는지 판정(결과 `results/cloud/01_gpu_probe.txt`)
- `Dockerfile` — 03장: 에이전트 이미지(상담 화면 + 그래프 + 창구 서버, 모델·임베더는 밖). `scripts/03-build.sh` 가 만들고 재서 `results/cloud/03_image.txt`
- `scripts/04-config.sh` — 04장: ConfigMap(창구 정의 `desk.yaml`) · Secret(모델 키)
- `manifests/04-console.yaml` — 04장: 상담 화면 Deployment + Service (05장은 replicas 만 늘림, 07장은 모델만 바꿈)
- `scripts/05-lb.sh` · `scripts/05-kill.sh` — 05장: 로드 밸런서 횟수 세기 · 승인 대기 중 Pod 죽이기
- `manifests/06-hpa.yaml` · `scripts/06-load.sh` — 06장: HPA(1→4, CPU 50%) · 부하 걸고 10초마다 Pod 수 기록
- `manifests/07-sglang.yaml` · `07-download.yaml` — 07장: SGLang GPU Pod + PVC(가중치) + Service · 가중치 내려받기 Job. 벤치마크 설정 `configs/serving_cloud_pod.yaml`(Pod) · `serving_cloud_host.yaml`(바탕: 호스트 Docker)
- 컨테이너에서 쓰는 환경 변수: `ONPREM_MODEL`(rule/sglang-4b/gateway) · `ONPREM_MODEL_URL`(모델 서버 주소) · `ONPREM_MODEL_KEY`(게이트웨이 키) · `ONPREM_EMBEDDER` · `ONPREM_DESKS`

`results/cloud/` 는 Git 에 올리지 않는다. 확정본은 `reports/cloud_*.md`.
