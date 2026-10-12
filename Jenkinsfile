// 12장: Jenkins 파이프라인 — 올릴 때(poll SCM) 단위·모듈 시험, 매일 밤 2시(cron) 전체 시험(노트북 GPU 일꾼 'laptop' 에서).
// 전체 시험은 GPU 와 메모리를 다 쓰므로, 시작 전에 클러스터의 모델 서버·상담 화면을 내리고 끝나면 올린다(deploy/scripts/12-quiet.sh).
pipeline {
  agent { label 'laptop' }
  options { timestamps(); disableConcurrentBuilds(); buildDiscarder(logRotator(numToKeepStr: '20')) }
  // 컨트롤러 Pod 의 시계는 UTC — TZ 를 적지 않으면 'H 2' 가 한국 시각 오전 11시가 된다(C12)
  triggers { pollSCM('H/5 * * * *'); cron('''TZ=Asia/Seoul
H 2 * * *''') }
  environment { PY = "${env.HOME}/onprem-agent/.venv/bin/python"; PYTHONPATH = "${env.WORKSPACE}/src" }   // 노트북 가상환경의 파이썬, 코드는 이 작업 공간의 것
  stages {
    stage('단위 시험') { steps { sh 'make test-unit PY=$PY' } }
    stage('모듈 시험') { steps { sh 'make test-module PY=$PY' } }
    stage('전체 시험 (밤)') {
      when { triggeredBy 'TimerTrigger' }
      steps {
        sh 'bash deploy/scripts/12-quiet.sh down'                       // 모델 서버 Pod · 상담 화면을 내려 GPU·메모리를 비운다
        sh 'make test-full PY=$PY CONFIG=configs/agent_laptop_w7_split.yaml NAME=agent_laptop_w7_split REF=results/reference || true'
        sh 'bash deploy/scripts/12-quiet.sh up'
        sh 'grep -h "빨간불 검사:" results/*_gate.md || true'
        script {
          def red = sh(script: 'grep -l "빨간불 검사: 빨간불" results/*_gate.md 2>/dev/null | wc -l', returnStdout: true).trim()
          if (red != '0') { error("빨간불 ${red}건 — results/*_gate.md 를 읽는다") }
        }
      }
    }
  }
  post {
    always { archiveArtifacts artifacts: 'results/*.md, results/*.json', allowEmptyArchive: true, fingerprint: false }
  }
}
