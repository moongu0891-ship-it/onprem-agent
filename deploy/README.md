# deploy/ — minikube 위에 에이전트 올리기 (8주차 워크북의 재료)

읽는 순서는 [docs/클라우드_실습_워크북.md](../docs/클라우드_실습_워크북.md). 여기 파일은 그 워크북의 장 번호를 따른다.

- `scripts/install-minikube.sh` — 00장: kubectl · minikube · helm 설치
- `scripts/probe-gpu.sh` — 01장: Pod 에서 GPU 가 보이는지 판정(결과 `results/cloud/01_gpu_probe.txt`)
- `manifests/` — 03장부터 장마다 더해진다

`results/cloud/` 는 Git 에 올리지 않는다. 확정본은 `reports/cloud_*.md`.
