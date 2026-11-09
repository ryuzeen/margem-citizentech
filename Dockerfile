# Imagem única do Margem: API + front + ponte MQTT + consumidor Kafka (muda só o comando).
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MARGEM_HOST=0.0.0.0 \
    MARGEM_PORTA=8080

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt kafka-python==2.0.6

COPY comum ./comum
COPY config ./config
COPY area1_ia ./area1_ia
COPY area2_bigdata ./area2_bigdata
COPY area3_mvp_iot ./area3_mvp_iot
COPY .env.example ./.env.example

# Segurança: o processo não roda como root.
RUN useradd --create-home --uid 1000 margem && mkdir -p /app/dados && chown -R margem:margem /app
USER margem

EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=4).status==200 else 1)"

CMD ["python", "-m", "area3_mvp_iot.api"]
