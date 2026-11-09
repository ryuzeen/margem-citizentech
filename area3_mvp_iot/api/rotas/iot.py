"""Ingestão IoT por HTTP (ESP32/simulador) e consulta das estações."""
import hmac
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, Query

from comum import territorio
from comum.config import token_estacao

from ..modelos import LeituraEntrada
from ..seguranca import LIMITE_IOT, erro, usuario_atual
from ..servicos import formatos
from ..servicos.estado import estado
from ..servicos.fluxo import LeituraRecusada, receber_leitura
from ..servicos.tarefas import simulacao

roteador = APIRouter(prefix="/iot", tags=["IoT"])


@roteador.post("/leituras", status_code=202)
def receber(leitura: LeituraEntrada, x_device_token: str | None = Header(default=None)):
    token = token_estacao(leitura.estacao_id)
    # 1ª barreira: token da estação no cabeçalho. 2ª: assinatura HMAC do corpo (validar_leitura).
    if not token or not x_device_token or not hmac.compare_digest(token, x_device_token):
        raise erro(401, "estacao_nao_autorizada", "Token da estação ausente ou inválido.")
    if not LIMITE_IOT.permitir(leitura.estacao_id):
        raise erro(429, "taxa_excedida", "Estação enviando acima do limite.")
    agora = simulacao.simulador.relogio if simulacao.simulador is not None else None
    try:
        resultado = receber_leitura(leitura.model_dump(), origem="http", agora=agora)
    except LeituraRecusada as exc:
        raise erro(422, "leitura_recusada", exc.motivo) from exc
    # leitura real (ESP32/Wokwi ou ponte MQTT): o simulador para de gerar esta estação por 10 min
    simulacao.registrar_real(leitura.estacao_id)
    return resultado


@roteador.get("/estacoes")
def estacoes(_: dict = Depends(usuario_atual)):
    return [formatos.estacao(est, estado.risco.get(est["bairro_id"])) for est in territorio.estacoes()]


@roteador.get("/leituras")
def leituras(estacao_id: str, horas: int = Query(24, ge=1, le=72), _: dict = Depends(usuario_atual)):
    if territorio.estacao(estacao_id) is None:
        raise erro(404, "estacao_desconhecida", "Estação não encontrada.")
    serie = estado.serie(estacao_id)
    if not serie:
        return []
    # janela medida no relógio das próprias leituras (simulado ou real, conforme a fonte da estação)
    limite = datetime.fromisoformat(serie[-1]["ts"]) - timedelta(hours=horas)
    return [formatos.leitura_publica(p) for p in serie if datetime.fromisoformat(p["ts"]) >= limite]
