#!/usr/bin/env bash
# 12장: Jenkins 를 helm 으로 올리고, 노트북 일꾼(agent) 접속 명령을 만들어 준다 → results/cloud/12_jenkins.txt
#   bash deploy/scripts/12-jenkins.sh            # 1) 올리기 + 일꾼 명령 출력
#   bash deploy/scripts/12-jenkins.sh agent      # 2) 노트북에서 일꾼 띄우기 (포트 8081 로 port-forward 한 채로, JDK 17 필요)
set -euo pipefail
OUT=results/cloud/12_jenkins.txt; mkdir -p results/cloud var
if [ "${1:-}" = "agent" ]; then
  command -v java >/dev/null || { echo "JDK 17 이 필요하다: sudo apt install -y openjdk-17-jre-headless"; exit 2; }
  mkdir -p "$HOME/jenkins-agent"
  curl -sfo var/agent.jar http://127.0.0.1:8081/jnlpJars/agent.jar
  SECRET=$(curl -sf -u admin:lab-admin http://127.0.0.1:8081/computer/laptop/jenkins-agent.jnlp | sed -n 's/.*<argument>\([a-f0-9]\{64\}\)<\/argument>.*/\1/p')
  echo "일꾼 'laptop' 접속(이 창을 열어 둔다, Ctrl+C 로 끝)"
  exec java -jar var/agent.jar -url http://127.0.0.1:8081/ -name laptop -secret "$SECRET" -workDir "$HOME/jenkins-agent" -webSocket
fi
{
  echo "== $(date '+%F %T')"
  helm repo add jenkins https://charts.jenkins.io >/dev/null 2>&1 || true; helm repo update >/dev/null
  t0=$(date +%s)
  helm upgrade --install jenkins jenkins/jenkins -n lab -f deploy/helm/jenkins-values.yaml --wait --timeout 600s
  echo "Jenkins Ready $(( $(date +%s)-t0 ))초"
  kubectl -n lab get pods -l app.kubernetes.io/component=jenkins-controller
  echo "다음: 다른 창에서  kubectl -n lab port-forward svc/jenkins 8081:8080   을 켜 두고,"
  echo "      bash deploy/scripts/12-jenkins.sh agent    로 노트북 일꾼을 붙인다. 화면 http://127.0.0.1:8081 (admin / lab-admin)"
} 2>&1 | tee -a "$OUT"
