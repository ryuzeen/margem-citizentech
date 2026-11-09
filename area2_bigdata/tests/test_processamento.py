"""Processamento: colunas do refinado, rótulo transbordo_2h, idempotência/dedup e incremental."""
import json
from datetime import datetime, timedelta

import pandas as pd

from area2_bigdata.features import COLUNAS_LEITURAS_HORA, agregar_hora, calcular_features, features_recentes
from area2_bigdata.ingestao import gravar_bruta, gravar_bruta_lote
from area2_bigdata.processamento import processar
from area2_bigdata.tempo import FUSO_BR
from area2_bigdata.tests.conftest import leitura_assinada, serie_horaria
from comum import territorio

PANTANAL = territorio.estacao("EST-PANTANAL-01")  # cota de alerta 260, transbordo 340


def _features(niveis, chuva=0.0):
    df = pd.DataFrame(serie_horaria(niveis, chuva=chuva))
    return calcular_features(agregar_hora(df), PANTANAL)


def test_rotulo_transbordo_2h():
    feats = _features([100, 100, 100, 350, 100, 100, 100])
    assert feats["transbordo_2h"].tolist() == [0, 1, 1, 0, 0, 0, 0]


def test_features_janelas_de_chuva_e_variacao():
    feats = _features([100, 110, 130, 160], chuva=10.0)
    ultima = feats.iloc[-1]
    assert ultima["chuva_3h"] == 30.0 and ultima["chuva_6h"] == 40.0 and ultima["chuva_24h"] == 40.0
    assert ultima["nivel_var_1h"] == 30.0 and ultima["nivel_var_3h"] == 60.0
    assert ultima["pct_cota_alerta"] == round(160 / 260 * 100, 2)
    assert feats.iloc[0]["nivel_var_1h"] == 0.0


def test_features_recentes_igual_ao_lote():
    leituras = serie_horaria([100, 120, 150, 200, 260], chuva=5.0)
    recente = features_recentes(leituras, PANTANAL)
    lote = _features([100, 120, 150, 200, 260], chuva=5.0).iloc[-1]
    assert recente["nivel_var_3h"] == lote["nivel_var_3h"] and recente["chuva_3h"] == lote["chuva_3h"]
    assert "transbordo_2h" not in recente and recente["hora"].endswith("-03:00")


def test_colunas_do_refinado_seguem_o_contrato(lake):
    gravar_bruta_lote("leituras", serie_horaria([100 + i for i in range(30)]), origem="historico")
    resumo = processar()
    lh = pd.read_parquet(lake / "data_lake" / "refinada" / "leituras_hora.parquet")
    assert list(lh.columns) == COLUNAS_LEITURAS_HORA
    assert resumo["leituras"]["aceitas"] == 30 and len(lh) == 30
    assert lh["hora"].iloc[0].utcoffset() == timedelta(hours=-3)
    for nome in ("risco_bairro.parquet", "indicadores.json", "powerbi/fato_leitura_hora.csv",
                 "powerbi/dim_bairro.csv", "powerbi/dim_estacao.csv"):
        assert (lake / "data_lake" / "refinada" / nome).exists()


def test_idempotencia_e_dedup(lake):
    serie = serie_horaria([100, 110, 120])
    gravar_bruta_lote("leituras", serie, origem="historico")
    processar()
    segunda = processar()
    assert segunda["leituras"]["novas_brutas"] == 0 and segunda["leituras"]["total_confiavel"] == 3
    # replay (mesmo seq) vai para a quarentena; mesmo ts com outro seq é deduplicado
    gravar_bruta("leituras", serie[0], origem="http")
    gravar_bruta("leituras", leitura_assinada(ts=serie[1]["ts"], seq=999, nivel=111.0), origem="http")
    terceira = processar()
    assert terceira["leituras"]["rejeitadas"] == 1 and terceira["leituras"]["duplicadas"] == 1
    assert terceira["leituras"]["total_confiavel"] == 3
    quarentena = pd.read_csv(lake / "data_lake" / "quarentena" / "leituras.csv")
    assert quarentena["motivo"].tolist() == ["seq_repetido"]
    assert quarentena["etapa"].tolist() == ["processamento"]
    # reconstrução completa não duplica a quarentena do processamento
    processar(completo=True)
    assert len(pd.read_csv(lake / "data_lake" / "quarentena" / "leituras.csv")) == 1


def test_incremental_igual_a_reconstrucao(lake):
    niveis = [100, 120, 160, 220, 300, 360, 380, 330, 250, 180, 140, 120]
    serie = serie_horaria(niveis, chuva=8.0)
    gravar_bruta_lote("leituras", serie[:5], origem="historico")
    processar()
    gravar_bruta_lote("leituras", serie[5:], origem="historico")
    processar()
    caminho = lake / "data_lake" / "refinada" / "leituras_hora.parquet"
    incremental = pd.read_parquet(caminho)
    processar(completo=True)
    pd.testing.assert_frame_equal(incremental, pd.read_parquet(caminho))
    assert incremental["transbordo_2h"].tolist() == [0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0]


def test_simulador_com_relogio_adiantado_nao_vai_para_quarentena(lake):
    futura = leitura_assinada(ts=datetime.now(FUSO_BR) + timedelta(hours=5), seq=1)
    gravar_bruta("leituras", futura, origem="simulador")
    gravar_bruta("leituras", leitura_assinada(ts=futura["ts"], seq=2), origem="http")
    resumo = processar()
    assert resumo["leituras"]["aceitas"] == 1 and resumo["leituras"]["rejeitadas"] == 1


def test_ocorrencia_atualizada_mantem_ultima_versao(lake):
    base = {"id": "OC-000001", "bairro_id": "jardim-pantanal", "texto": "água entrando em casa",
            "criado_em": "2026-11-04T10:00:00-03:00", "status": "aberta",
            "triagem": {"categoria": "agua_na_residencia", "gravidade": 3, "prioridade": 60,
                        "vulneraveis": ["idoso"]}}
    gravar_bruta("ocorrencias", base, origem="api")
    gravar_bruta("leituras", leitura_assinada(), origem="http")
    processar()
    gravar_bruta("ocorrencias", dict(base, status="em_atendimento", atendido_em="2026-11-04T10:20:00-03:00"),
                 origem="api")
    processar()
    oc = pd.read_parquet(lake / "data_lake" / "confiavel" / "ocorrencias.parquet")
    assert len(oc) == 1 and oc.iloc[0]["status"] == "em_atendimento" and oc.iloc[0]["vulneraveis"] == "idoso"
    indic = json.loads((lake / "data_lake" / "refinada" / "indicadores.json").read_text(encoding="utf-8"))
    assert indic["tempo_atendimento"]["tempo_medio_min"] == 20.0
