# Medidas do dashboard (contrato §9) — Python × DAX

Implementação Python: `area2_bigdata/analytics/medidas.py` → `indicadores(bairro_id, de, ate, estacao_id, extras)`.
O processamento grava a versão sem filtro em `dados/data_lake/refinada/indicadores.json`; a API chama a função
com os filtros do usuário e injeta dados ao vivo em `extras` (ocorrências, check-ins, risco atual).
**Todos os dados são simulados** (histórico de 365 dias gerado por `area2_bigdata/historico`).

## Modelo de dados do Power BI (`refinada/powerbi/*.csv`)
CSVs em UTF-8, separador vírgula, **decimal ponto** e datas `AAAA-MM-DD HH:MM:SS` (horário -03:00). No Power
Query, importe com localidade **Inglês (Estados Unidos)** para o ponto decimal ser lido corretamente.

| tabela | grão | colunas principais |
|---|---|---|
| `dim_bairro` | 1 por bairro | bairro_id, nome, lat, lng, populacao_estimada, domicilios_area_risco, estacao_id |
| `dim_estacao` | 1 por estação | estacao_id, bairro_id, nome, altura_instalacao_cm, cota_alerta_cm, cota_transbordo_cm, nivel_base_cm |
| `fato_leitura_hora` | estação × hora | features do §5 (nivel_cm … transbordo_2h) + data, prob_2h, nivel_cota, nivel_risco |
| `fato_ocorrencia` | 1 por ocorrência | id, bairro_id, categoria, gravidade, prioridade, vulneraveis, status, criado_em, atendido_em, resolvido_em, tempo_atendimento_min, atendida_ate_30min, data |
| `fato_alerta` | 1 por alerta | id, bairro_id, estacao_id, nivel, nivel_cm, motivo, emitido_em, encerrado_em, data |
| `dim_morador` | 1 por cadastro | id, bairro_id, telefone_mascarado, vulnerabilidades, idoso, pcd, crianca, gestante, acamado, em_area_risco, canal_preferido, cadastrado_em |
| `fato_checkin` | 1 por check-in | só existe quando a API gravou check-ins na camada bruta (`tipo="checkins"`) |

Relacionamentos (1 → *): `dim_bairro[bairro_id]` → `fato_leitura_hora`, `fato_ocorrencia`, `fato_alerta`,
`dim_morador`, `fato_checkin`; `dim_estacao[estacao_id]` → `fato_leitura_hora[estacao_id]`.
Filtros do painel = segmentações por `dim_bairro[nome]`, `dim_estacao[nome]` e período (`data`).

Colunas calculadas usadas pelas medidas (em `fato_leitura_hora`):

```dax
nivel_ordem =
SWITCH (
    fato_leitura_hora[nivel_risco],
    "observacao", 0,
    "atencao", 1,
    "alerta", 2,
    "alerta_maximo", 3,
    BLANK ()
)

inicio_transbordo =
VAR Est = fato_leitura_hora[estacao_id]
VAR H = fato_leitura_hora[hora]
VAR Cota = RELATED ( dim_estacao[cota_transbordo_cm] )
VAR NivelAnterior =
    CALCULATE (
        MAX ( fato_leitura_hora[nivel_cm] ),
        FILTER (
            ALL ( fato_leitura_hora ),
            fato_leitura_hora[estacao_id] = Est
                && fato_leitura_hora[hora] >= H - TIME ( 1, 0, 0 )
                && fato_leitura_hora[hora] < H
        )
    )
RETURN
    IF (
        fato_leitura_hora[nivel_cm] >= Cota
            && ( ISBLANK ( NivelAnterior ) || NivelAnterior < Cota ),
        1,
        0
    )
```

---

## 1. Nível vs cota (por estação)
**Fórmula:** nível atual = média das leituras da última hora; % da cota = nível ÷ cota de alerta × 100;
horas acima do alerta = nº de horas com nível ≥ cota de alerta; transbordos = nº de inícios de sequência com
nível ≥ cota de transbordo. Série: nível e % da cota por hora (agregada pelo máximo de 6 h quando o período
passa de 7 dias).

```python
ultimo = dados.sort_values("hora").iloc[-1]
pct = ultimo["nivel_cm"] / est["cota_alerta_cm"] * 100
horas_acima = (dados["nivel_cm"] >= est["cota_alerta_cm"]).sum()
acima = dados["nivel_cm"] >= est["cota_transbordo_cm"]
transbordos = (acima & ~acima.shift(fill_value=False)).sum()
```

```dax
Nivel Atual (cm) =
VAR UltimaHora = MAX ( fato_leitura_hora[hora] )
RETURN
    CALCULATE ( AVERAGE ( fato_leitura_hora[nivel_cm] ), fato_leitura_hora[hora] = UltimaHora )

% da Cota de Alerta =
AVERAGEX (
    VALUES ( dim_estacao[estacao_id] ),
    VAR Cota = CALCULATE ( MAX ( dim_estacao[cota_alerta_cm] ) )
    RETURN DIVIDE ( [Nivel Atual (cm)], Cota ) * 100
)

Horas Acima do Alerta =
SUMX (
    VALUES ( dim_estacao[estacao_id] ),
    VAR Cota = CALCULATE ( MAX ( dim_estacao[cota_alerta_cm] ) )
    RETURN CALCULATE ( COUNTROWS ( fato_leitura_hora ), fato_leitura_hora[nivel_cm] >= Cota )
)

Transbordos =
CALCULATE ( COUNTROWS ( fato_leitura_hora ), fato_leitura_hora[inicio_transbordo] = 1 )
```

## 2. Risco previsto por bairro (próximas 2 h)
**Fórmula:** nível final = o **maior** entre a regra por cota (≥ 60 % do alerta = atenção, ≥ alerta = alerta,
≥ transbordo = alerta máximo) e a regra por probabilidade do modelo (prob ≥ 0,35 / 0,60 / 0,85). Ranking =
último nível e última `prob_2h` de cada bairro; horas por nível no período.

```python
nivel_cota = nivel_por_cota(nivel_cm, cota_alerta, cota_transbordo)          # comum.niveis
nivel = maior_nivel(nivel_cota, nivel_por_probabilidade(prob)) if prob is not None else nivel_cota
horas_por_nivel = {n: (dados["nivel"] == n).sum() for n in NIVEIS}
```

```dax
Prob Transbordo 2h =
VAR UltimaHora = MAX ( fato_leitura_hora[hora] )
RETURN
    CALCULATE ( MAX ( fato_leitura_hora[prob_2h] ), fato_leitura_hora[hora] = UltimaHora )

Ordem Risco Atual =
VAR Nivel = [Nivel Atual (cm)]
VAR CotaAlerta = MAX ( dim_estacao[cota_alerta_cm] )
VAR CotaTransbordo = MAX ( dim_estacao[cota_transbordo_cm] )
VAR Prob = [Prob Transbordo 2h]
VAR PorCota =
    SWITCH (
        TRUE (),
        Nivel >= CotaTransbordo, 3,
        Nivel >= CotaAlerta, 2,
        Nivel >= 0.6 * CotaAlerta, 1,
        0
    )
VAR PorProb =
    SWITCH ( TRUE (), ISBLANK ( Prob ), 0, Prob >= 0.85, 3, Prob >= 0.60, 2, Prob >= 0.35, 1, 0 )
RETURN
    IF ( ISBLANK ( Nivel ), BLANK (), MAX ( PorCota, PorProb ) )

Nivel de Risco Atual =
SWITCH ( [Ordem Risco Atual], 0, "Observação", 1, "Atenção", 2, "Alerta", 3, "Alerta máximo", "Sem dados" )

Horas em Alerta =
CALCULATE (
    COUNTROWS ( fato_leitura_hora ),
    fato_leitura_hora[nivel_risco] IN { "alerta", "alerta_maximo" }
)
```

## 3. Ocorrências por categoria × gravidade × status
**Fórmula:** contagem de ocorrências distintas (por `id`) cruzando categoria, gravidade (1–5) e status;
graves = gravidade ≥ 4; abertas = status diferente de resolvida. Série diária por `criado_em`.

```python
matriz = oc.groupby(["categoria", "gravidade", "status"]).size()
graves = (oc["gravidade"] >= 4).sum()
```

```dax
Ocorrencias = DISTINCTCOUNT ( fato_ocorrencia[id] )

Ocorrencias Graves (4-5) =
CALCULATE ( [Ocorrencias], fato_ocorrencia[gravidade] >= 4 )

Ocorrencias Abertas =
CALCULATE ( [Ocorrencias], fato_ocorrencia[status] <> "resolvida" )
```
Visual sugerido: matriz com `categoria` nas linhas, `gravidade` nas colunas e segmentação por `status`.

## 4. Tempo médio até atendimento e % em até 30 min
**Fórmula:** tempo = `atendido_em − criado_em` em minutos, só nas ocorrências já atendidas; média; % em até
30 min = atendidas com tempo ≤ 30 ÷ atendidas × 100.

```python
atend = oc.dropna(subset=["atendido_em"])
minutos = (atend["atendido_em"] - atend["criado_em"]).dt.total_seconds() / 60
tempo_medio, pct_30 = minutos.mean(), (minutos <= 30).mean() * 100
```

```dax
Tempo Medio Atendimento (min) =
AVERAGEX (
    FILTER ( fato_ocorrencia, NOT ISBLANK ( fato_ocorrencia[atendido_em] ) ),
    ( fato_ocorrencia[atendido_em] - fato_ocorrencia[criado_em] ) * 1440
)

% Atendidas em 30 min =
VAR Atendidas =
    CALCULATE ( COUNTROWS ( fato_ocorrencia ), NOT ISBLANK ( fato_ocorrencia[atendido_em] ) )
VAR Rapidas =
    CALCULATE ( COUNTROWS ( fato_ocorrencia ), fato_ocorrencia[tempo_atendimento_min] <= 30 )
RETURN
    IF ( Atendidas = 0, BLANK (), DIVIDE ( Rapidas, Atendidas ) * 100 )
```
(`* 1440` converte a diferença de datas, em dias, para minutos — igual ao `total_seconds() / 60`.)

## 5. Vulneráveis em área de risco e % com check-in
**Fórmula:** vulneráveis em risco = moradores com ≥ 1 vulnerabilidade (idoso, pcd, criança, gestante,
acamado), marcados em área de risco, de bairros cujo risco **atual** é ≥ alerta. % check-in = pessoas distintas
com check-in nesses bairros ÷ vulneráveis em risco × 100 (limitado a 100). Também: vulneráveis expostos no
período (bairros que chegaram a ≥ alerta em alguma hora do período).

```python
vuln = moradores[(moradores["vulnerabilidades"] != "") & moradores["em_area_risco"]]
em_risco = vuln[vuln["bairro_id"].isin(bairros_em_alerta)]
pct = min(100, pessoas_com_checkin / len(em_risco) * 100)
```

```dax
Vulneraveis em Risco =
VAR BairrosEmAlerta =
    FILTER ( VALUES ( dim_bairro[bairro_id] ), [Ordem Risco Atual] >= 2 )
RETURN
    CALCULATE (
        COUNTROWS ( dim_morador ),
        dim_morador[vulnerabilidades] <> "",
        dim_morador[em_area_risco] = TRUE (),
        KEEPFILTERS ( TREATAS ( BairrosEmAlerta, dim_morador[bairro_id] ) )
    )

% Check-in Vulneraveis =
VAR BairrosEmAlerta =
    FILTER ( VALUES ( dim_bairro[bairro_id] ), [Ordem Risco Atual] >= 2 )
VAR ComCheckin =
    CALCULATE (
        DISTINCTCOUNT ( fato_checkin[usuario_id] ),
        KEEPFILTERS ( TREATAS ( BairrosEmAlerta, fato_checkin[bairro_id] ) )
    )
VAR Total = [Vulneraveis em Risco]
RETURN
    IF ( Total = 0, BLANK (), MIN ( 100, DIVIDE ( ComCheckin, Total ) * 100 ) )
```
Sem `fato_checkin` (histórico não tem check-ins), use só `Vulneraveis em Risco`; no dashboard web os
check-ins vêm ao vivo da API (`extras["checkins"]`).

## 6. Antecedência do alerta (modelo × regra só por cota)
**Fórmula:** para cada transbordo (1ª hora com nível ≥ cota de transbordo), antecedência = minutos entre o
início da sequência contínua de horas em ≥ alerta imediatamente anterior (limite 24 h) e a hora do transbordo.
Calculada duas vezes: com o nível **só por cota** (`nivel_cota`) e com o nível **final** com o modelo
(`nivel_risco`). Ganho = média modelo − média cota.

```python
inicio = idx
while inicio > 0 and em_alerta[inicio - 1] and horas[inicio] - horas[inicio - 1] == 1h \
        and horas[idx] - horas[inicio - 1] <= 24h:
    inicio -= 1
antecedencia_min = (horas[idx] - horas[inicio]).total_seconds() / 60
```

Colunas calculadas em `fato_leitura_hora` (a de modelo é igual trocando `nivel_cota` por `nivel_risco`):

```dax
antecedencia_cota_min =
VAR Est = fato_leitura_hora[estacao_id]
VAR H = fato_leitura_hora[hora]
VAR UltimaForaDoAlerta =
    CALCULATE (
        MAX ( fato_leitura_hora[hora] ),
        FILTER (
            ALL ( fato_leitura_hora ),
            fato_leitura_hora[estacao_id] = Est
                && fato_leitura_hora[hora] < H
                && fato_leitura_hora[hora] >= H - 1
                && NOT ( fato_leitura_hora[nivel_cota] IN { "alerta", "alerta_maximo" } )
        )
    )
VAR InicioAlerta = IF ( ISBLANK ( UltimaForaDoAlerta ), H - 1, UltimaForaDoAlerta + TIME ( 1, 0, 0 ) )
RETURN
    IF ( fato_leitura_hora[inicio_transbordo] = 1, ( H - InicioAlerta ) * 1440 )
```

```dax
Antecedencia Media Cota (min) = AVERAGE ( fato_leitura_hora[antecedencia_cota_min] )

Antecedencia Media Modelo (min) = AVERAGE ( fato_leitura_hora[antecedencia_modelo_min] )

Ganho de Antecedencia =
VAR Cota = [Antecedencia Media Cota (min)]
VAR Modelo = [Antecedencia Media Modelo (min)]
RETURN
    IF ( ISBLANK ( Cota ), BLANK (), Modelo - Cota )
```
Diferença conhecida: a versão DAX não exige horas consecutivas (o Python interrompe a sequência em lacunas de
dados); com o histórico horário completo os resultados coincidem.
