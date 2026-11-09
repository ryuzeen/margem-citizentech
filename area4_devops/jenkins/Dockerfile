# Jenkins do Margem: já vem com Python (testes), Docker CLI + Compose (build/deploy) e o job configurado (JCasC).
# Docker CLI e Compose vêm da imagem oficial docker:cli (binários estáticos), sem depender de download externo.
FROM docker:27.4.1-cli AS dockercli

FROM jenkins/jenkins:2.541.3-lts-jdk17

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv python3-pip ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/lib/docker/cli-plugins/docker-compose
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
COPY casc.yaml /var/jenkins_home/casc.yaml
COPY casc.yaml /usr/share/jenkins/ref/casc.yaml
