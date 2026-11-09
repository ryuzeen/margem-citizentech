"""Testes da API (casos do plano de testes CT-API-*)."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from area3_mvp_iot.api import seguranca
from area3_mvp_iot.api.app import criar_app
from comum.config import token_estacao
from comum.seguranca_iot import assinar

FUSO = timezone(timedelta(hours=-3))
CIDADAO = {"email": "maria@demo.margem.app", "senha": "Margem@2026"}
DEFESA = {"email": "operador@demo.margem.app", "senha": "DefesaCivil@2026"}


@pytest.fixture(scope="module")
def cliente():
    with TestClient(criar_app()) as c:
        yield c


@pytest.fixture(autouse=True)
def _zerar_limites():
    for limitador in (seguranca.LIMITE_LOGIN, seguranca.LIMITE_RELATOS, seguranca.LIMITE_IOT):
        limitador.limpar()


def _token(cliente, credenciais):
    resposta = cliente.post("/api/v1/auth/login", json=credenciais)
    assert resposta.status_code == 200, resposta.text
    return {"Authorization": f"Bearer {resposta.json()['token']}"}


_seq = iter(range(10_000, 99_999))


def _leitura(estacao_id="EST-PANTANAL-01", nivel=150.0, **extra):
    leitura = {
        "estacao_id": estacao_id,
        "ts": datetime.now(FUSO).isoformat(timespec="seconds"),
        "seq": next(_seq),
        "nivel_cm": nivel,
        "chuva_mm_h": 20.0,
        "umidade_solo_pct": 80.0,
        "bateria_pct": 90,
        "firmware": "1.0.0",
    }
    leitura.update(extra)
    leitura["sig"] = assinar(leitura, token_estacao(estacao_id))
    return leitura


def test_health_e_cabecalhos_de_seguranca(cliente):
    r = cliente.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_login_invalido_nao_revela_se_email_existe(cliente):
    a = cliente.post("/api/v1/auth/login", json={"email": "ninguem@x.com", "senha": "Errada123"})
    b = cliente.post("/api/v1/auth/login", json={"email": CIDADAO["email"], "senha": "Errada123"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_login_tem_limite_de_tentativas(cliente):
    codigos = [cliente.post("/api/v1/auth/login", json={"email": "x@x.com", "senha": "a"}).status_code
               for _ in range(12)]
    assert 429 in codigos


def test_cadastro_exige_consentimento_e_recusa_campo_extra(cliente):
    base = {"nome": "João Teste", "email": "joao@teste.com", "senha": "Senha1234", "bairro_id": "vila-itaim"}
    r = cliente.post("/api/v1/auth/cadastro", json=base | {"consentimento_lgpd": False})
    assert r.status_code == 422
    r = cliente.post("/api/v1/auth/cadastro", json=base | {"consentimento_lgpd": True, "papel": "defesa_civil"})
    assert r.status_code == 422  # tentativa de virar Defesa Civil pelo cadastro
    r = cliente.post("/api/v1/auth/cadastro", json=base | {"consentimento_lgpd": True})
    assert r.status_code == 201 and r.json()["usuario"]["papel"] == "cidadao"
    assert "senha_hash" not in r.json()["usuario"]


def test_cidadao_nao_acessa_console(cliente):
    h = _token(cliente, CIDADAO)
    assert cliente.get("/api/v1/dashboard/indicadores", headers=h).status_code == 403
    assert cliente.get("/api/v1/checkins", headers=h).status_code == 403
    assert cliente.get("/api/v1/dashboard/indicadores").status_code == 401


def test_iot_recusa_token_errado(cliente):
    r = cliente.post("/api/v1/iot/leituras", json=_leitura(), headers={"X-Device-Token": "errado"})
    assert r.status_code == 401


def test_iot_recusa_assinatura_adulterada(cliente):
    leitura = _leitura()
    leitura["nivel_cm"] = 999.0  # alterado depois de assinado
    r = cliente.post("/api/v1/iot/leituras", json=leitura,
                     headers={"X-Device-Token": token_estacao("EST-PANTANAL-01")})
    assert r.status_code == 422


def test_iot_leitura_valida_atualiza_risco(cliente):
    h = {"X-Device-Token": token_estacao("EST-PANTANAL-01")}
    r = cliente.post("/api/v1/iot/leituras", json=_leitura(nivel=350.0), headers=h)
    assert r.status_code == 202, r.text
    risco = {b["bairro_id"]: b for b in cliente.get("/api/v1/risco/atual").json()}
    assert risco["jardim-pantanal"]["nivel"] == "alerta_maximo"  # acima da cota de transbordo (340)
    alertas = cliente.get("/api/v1/alertas", params={"bairro_id": "jardim-pantanal"}).json()
    assert alertas and len(alertas[0]["mensagem_curta"]) <= 160


def test_iot_recusa_replay(cliente):
    h = {"X-Device-Token": token_estacao("EST-ITAIM-01")}
    leitura = _leitura("EST-ITAIM-01")
    assert cliente.post("/api/v1/iot/leituras", json=leitura, headers=h).status_code == 202
    assert cliente.post("/api/v1/iot/leituras", json=leitura, headers=h).status_code == 422


def test_relato_passa_pelos_agentes_e_entra_na_fila(cliente):
    h = _token(cliente, CIDADAO)
    texto = "A água tá entrando em casa e minha mãe é cadeirante, não consigo tirar ela sozinha"
    r = cliente.post("/api/v1/ocorrencias", json={"texto": texto}, headers=h)
    assert r.status_code == 201, r.text
    triagem = r.json()["triagem"]
    assert "pcd" in triagem["vulneraveis"]
    assert triagem["gravidade"] >= 4
    assert {p["agente"] for p in triagem["rastro"]} >= {"triagem", "protocolos", "prioridade"}

    fila = cliente.get("/api/v1/ocorrencias", headers=_token(cliente, DEFESA)).json()
    prioridades = [o["prioridade_efetiva"] for o in fila]
    assert prioridades == sorted(prioridades, reverse=True)


def test_relato_recusa_texto_curto(cliente):
    h = _token(cliente, CIDADAO)
    assert cliente.post("/api/v1/ocorrencias", json={"texto": "oi"}, headers=h).status_code == 422


def test_checkin_aparece_mascarado_no_console(cliente):
    cliente.post("/api/v1/checkins", json={"status": "preciso_ajuda"}, headers=_token(cliente, CIDADAO))
    checkins = cliente.get("/api/v1/checkins", headers=_token(cliente, DEFESA)).json()
    maria = next(c for c in checkins if c["nome"].startswith("Maria"))
    assert maria["status"] == "preciso_ajuda"
    assert "98765" not in maria["telefone_mascarado"] and maria["nome"] == "Maria S."
    assert {"bairro_id", "vulnerabilidades", "obs", "criado_em"} <= set(maria)
    assert "usuario_id" not in maria and "telefone" not in maria and "email" not in maria


def test_rascunho_e_emissao_de_alerta(cliente):
    h = _token(cliente, DEFESA)
    rascunho = cliente.post("/api/v1/alertas/rascunho", json={"bairro_id": "jardim-romano"}, headers=h).json()
    assert len(rascunho["mensagem_curta"]) <= 160
    corpo = {k: rascunho[k] for k in ("titulo", "mensagem_curta", "mensagem_completa")}
    r = cliente.post("/api/v1/alertas", json=corpo | {"bairro_id": "jardim-romano", "nivel": "atencao"}, headers=h)
    assert r.status_code == 201 and r.json()["origem"] == "manual"


def test_dashboard_filtra_por_bairro(cliente):
    h = _token(cliente, DEFESA)
    r = cliente.get("/api/v1/dashboard/indicadores", params={"bairro_id": "vila-itaim"}, headers=h)
    assert r.status_code == 200
    assert cliente.get("/api/v1/dashboard/indicadores", params={"bairro_id": "xx"}, headers=h).status_code == 422


def test_risco_atual_tem_campos_do_front(cliente):
    h = {"X-Device-Token": token_estacao("EST-ROMANO-01")}
    resp = cliente.post("/api/v1/iot/leituras", json=_leitura("EST-ROMANO-01", nivel=120.0), headers=h)
    assert resp.status_code == 202
    risco = {b["bairro_id"]: b for b in cliente.get("/api/v1/risco/atual").json()}
    romano = risco["jardim-romano"]
    for campo in ("nivel", "prob", "tendencia", "atualizado_em", "nivel_cm", "cota_alerta_cm", "cota_transbordo_cm",
                  "pct_cota_alerta", "variacao_1h_cm", "chuva_mm_h", "estacao_id"):
        assert campo in romano, campo
    assert romano["estacao_id"] == "EST-ROMANO-01" and 0 < romano["pct_cota_alerta"] < 1  # fração da cota
    assert len(risco) == 4 and all("cota_alerta_cm" in r for r in risco.values())  # inclusive sem leitura


def test_fila_tem_campos_do_front_e_respeita_lgpd(cliente):
    criada = cliente.post("/api/v1/ocorrencias", json={"texto": "Rua alagada na frente de casa, a água sobe rápido"},
                          headers=_token(cliente, CIDADAO)).json()
    assert criada["usuario_id"] and criada["origem"] == "app"  # o próprio morador vê o seu id
    h = _token(cliente, DEFESA)
    fila = cliente.get("/api/v1/ocorrencias", headers=h).json()
    oc = next(o for o in fila if o["id"] == criada["id"])
    for campo in ("usuario_nome", "origem", "atendido_em", "resolvido_em", "atualizado_em", "triagem"):
        assert campo in oc, campo
    assert oc["usuario_nome"] == "Maria S." and "usuario_id" not in oc and "morador" not in oc
    assert any(o["origem"] == "simulado" and o["usuario_nome"] is None for o in fila)  # relatos do seed
    # ordem do front: status, depois prioridade (recalculada) desc
    ordem = {"aberta": 0, "em_atendimento": 1, "resolvida": 2}
    chaves = [(ordem[o["status"]], -o["triagem"]["prioridade"]) for o in fila]
    assert chaves == sorted(chaves)
    # atender congela a prioridade; resolver entra no histórico da fila (o front filtra "Resolvidas")
    atendida = cliente.patch(f"/api/v1/ocorrencias/{oc['id']}", json={"status": "em_atendimento"}, headers=h).json()
    assert atendida["atendido_em"] and atendida["status"] == "em_atendimento" and "usuario_id" not in atendida
    resolvida = cliente.patch(f"/api/v1/ocorrencias/{oc['id']}", json={"status": "resolvida"}, headers=h).json()
    assert resolvida["resolvido_em"] and resolvida["atendido_em"] == atendida["atendido_em"]
    assert any(o["id"] == oc["id"] and o["status"] == "resolvida"
               for o in cliente.get("/api/v1/ocorrencias", headers=h).json())


def test_alerta_rascunho_e_publico_no_formato_do_front(cliente):
    h = _token(cliente, DEFESA)
    rascunho = cliente.post("/api/v1/alertas/rascunho", json={"bairro_id": "jardim-helena"}, headers=h).json()
    assert {"bairro_id", "nivel", "prob", "rastro"} <= set(rascunho)
    assert rascunho["rastro"][0]["agente"] == "comunicador" and "ms" in rascunho["rastro"][0]
    corpo = {k: rascunho[k] for k in ("titulo", "mensagem_curta", "mensagem_completa")}
    emitido = cliente.post("/api/v1/alertas", json=corpo | {"bairro_id": "jardim-helena", "nivel": "alerta"},
                           headers=h).json()
    for campo in ("id", "nivel", "origem", "prob", "emitido_em", "valido_ate", "destinatarios"):
        assert campo in emitido, campo
    publicos = cliente.get("/api/v1/alertas", params={"bairro_id": "jardim-helena"}).json()
    assert publicos and all("emitido_por" not in a for a in publicos)  # não expõe quem emitiu


def test_estacoes_tem_estado_e_bateria(cliente):
    h = {"X-Device-Token": token_estacao("EST-HELENA-01")}
    cliente.post("/api/v1/iot/leituras", json=_leitura("EST-HELENA-01", nivel=90.0, bateria_pct=12), headers=h)
    estacoes = {e["id"]: e for e in cliente.get("/api/v1/iot/estacoes", headers=_token(cliente, CIDADAO)).json()}
    helena = estacoes["EST-HELENA-01"]
    assert helena["estado"] == "bateria_baixa" and helena["bateria_pct"] == 12
    assert "sig" not in helena["ultima_leitura"] and helena["fonte"] == "real"
    assert all(e["estado"] in ("online", "bateria_baixa", "offline") for e in estacoes.values())


def test_simulacao_cenario_get(cliente):
    atual = cliente.get("/api/v1/simulacao/cenario").json()
    assert {"cenario", "desde", "relogio", "taxa"} <= set(atual)
    h = _token(cliente, DEFESA)
    assert cliente.post("/api/v1/simulacao/cenario", json={"cenario": "chuva_forte"}, headers=h).status_code == 200
    assert cliente.get("/api/v1/simulacao/cenario").json()["cenario"] == "chuva_forte"
    cliente.post("/api/v1/simulacao/cenario", json={"cenario": "normal"}, headers=h)


def test_indicadores_no_formato_do_front(cliente):
    h = _token(cliente, DEFESA)
    ind = cliente.get("/api/v1/dashboard/indicadores", headers=h,
                      params={"de": "2026-08-01T00:00:00-03:00", "ate": "2026-11-05T00:00:00-03:00"}).json()
    for campo in ("ocorrencias_periodo", "ocorrencias_abertas", "tempo_medio_atendimento_min", "pct_atendidas_30min",
                  "vulneraveis_area_risco", "pct_vulneraveis_checkin", "antecedencia_modelo_min",
                  "antecedencia_cota_min", "bairros_em_alerta"):
        assert campo in ind["kpis"], campo
    assert isinstance(ind["nivel_vs_cota"], list) and isinstance(ind["risco_bairro"], list)
    assert all({"prob", "tendencia", "nome"} <= set(r) for r in ind["risco_bairro"])
    assert {c["categoria"] for c in ind["ocorrencias"]["por_categoria"]} >= {"agua_na_residencia", "via_alagada"}
    assert set(ind["ocorrencias"]["por_status"]) == {"aberta", "em_atendimento", "resolvida"}
    assert isinstance(ind["tempo_atendimento"]["por_semana"], list)
    assert 0 <= ind["tempo_atendimento"]["pct_ate_30min"] <= 1  # fração, não %
    assert "por_tipo" in ind["vulneraveis"] and "eventos" in ind["antecedencia"]
    for chave in ("nivel_vs_cota", "risco_bairro", "ocorrencias", "tempo_atendimento", "vulneraveis", "antecedencia"):
        formula = ind["formulas"][chave]
        assert formula["titulo"] and formula["formula"] and formula["dax"], chave
    assert "DISTINCTCOUNT" in ind["formulas"]["ocorrencias"]["dax"]  # DAX real do MEDIDAS.md


def test_stream_ticket_exige_login_e_e_de_uso_unico(cliente):
    from area3_mvp_iot.api.servicos.estado import estado

    assert cliente.post("/api/v1/stream/ticket").status_code == 401
    ticket = cliente.post("/api/v1/stream/ticket", headers=_token(cliente, DEFESA)).json()["ticket"]
    assert estado.usar_ticket(ticket)["papel"] == "defesa_civil"
    assert estado.usar_ticket(ticket) is None


def test_estacao_real_pausa_o_simulador(cliente):
    from area3_mvp_iot.api.servicos.estado import estado
    from area3_mvp_iot.api.servicos.tarefas import Simulacao, simulacao

    h = {"X-Device-Token": token_estacao("EST-PANTANAL-01")}
    assert cliente.post("/api/v1/iot/leituras", json=_leitura(nivel=140.0), headers=h).status_code == 202
    assert "EST-PANTANAL-01" in simulacao.estacoes_reais()  # a rota HTTP registra a estação como real

    sim = Simulacao()
    sim.ativa = False  # não troca o relógio global da API no teste
    sim.registrar_real("EST-PANTANAL-01")
    antes = {e: len(estado.serie(e)) for e in ("EST-PANTANAL-01", "EST-ITAIM-01")}
    sim.tick()
    assert estado.ultima("EST-PANTANAL-01")["seq"] == estado.serie("EST-PANTANAL-01")[-1]["seq"]
    assert len(estado.serie("EST-PANTANAL-01")) == antes["EST-PANTANAL-01"]  # simulador não gerou a estação real
    assert estado.origem["EST-ITAIM-01"] == "simulador" and estado.origem["EST-PANTANAL-01"] == "real"
    sim.pausa_real_s = 0  # passados os 10 min, o simulador volta a gerar a estação
    assert sim.estacoes_reais() == []


def test_metricas_prometheus(cliente):
    texto = cliente.get("/api/v1/metrics").text
    assert "margem_leituras_total" in texto and "margem_http_duracao_segundos" in texto
