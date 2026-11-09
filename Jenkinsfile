// Pipeline do Margem (Jenkins). Disparado automaticamente por commit na main (pollSCM a cada 2 min).
pipeline {
  agent any
  options {
    timestamps()
    timeout(time: 30, unit: 'MINUTES')
    buildDiscarder(logRotator(numToKeepStr: '20'))
  }
  environment {
    VENV = "${WORKSPACE}/.venv"
    MARGEM_TAREFAS_FUNDO = '0'
    MARGEM_SIMULACAO = '0'
  }
  stages {
    stage('Ambiente') {
      steps {
        sh 'python3 -m venv "$VENV"'
        sh '"$VENV/bin/pip" install -q -r requirements-dev.txt'
      }
    }
    stage('Qualidade (lint)') {
      steps {
        sh '"$VENV/bin/ruff" check . --output-format=concise | tee ruff.txt'
      }
    }
    stage('Testes') {
      steps {
        sh '"$VENV/bin/python" -m pytest -m "not e2e" --junitxml=relatorios/junit.xml --cov=. --cov-report=xml:relatorios/cobertura.xml --cov-report=term'
      }
      post {
        always {
          junit 'relatorios/junit.xml'
          recordCoverage(tools: [[parser: 'COBERTURA', pattern: 'relatorios/cobertura.xml']])
        }
      }
    }
    stage('Build da imagem') {
      steps {
        sh 'docker build -t margem/app:${BUILD_NUMBER} -t margem/app:latest .'
      }
    }
    stage('Deploy') {
      steps {
        sh 'docker compose -p margem up -d --no-build api'
      }
    }
    stage('Smoke test') {
      steps {
        sh '''
          for i in $(seq 1 30); do
            if docker exec margem-api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=3)"; then
              echo "API no ar"; exit 0
            fi
            sleep 2
          done
          echo "API não respondeu"; exit 1
        '''
      }
    }
  }
  post {
    always {
      archiveArtifacts artifacts: 'ruff.txt, relatorios/**', allowEmptyArchive: true
    }
  }
}
