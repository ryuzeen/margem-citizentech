"""Modelo hidrológico SIMULADO das estações da várzea do Tietê.

Não é um modelo calibrado com dados reais: serve para gerar um histórico verossímil e alimentar o
simulador em tempo real. Componentes:

- **Chuva regional** (processo de eventos): estação chuvosa nov–mar (climatologia mensal aproximada de
  São Paulo), tempestades convectivas concentradas no fim da tarde, chuvas frontais longas e fracas e
  eventos extremos raros. Cada estação recebe a chuva regional com variação local.
- **Umidade do solo**: acumula com a chuva e seca exponencialmente sem ela; controla o escoamento.
- **Nível do rio**: cascata de dois reservatórios lineares (dá o atraso entre chuva e pico do rio)
  + reservatório lento (cheia acumulada de vários dias) + ondas de cheia vindas de montante (chuva na
  cabeceira do Tietê: sobem devagar e costumam passar do alerta sem transbordar = falsos alarmes da cota)
  somados ao nível base da estação (`config/territorio.json`).

Cenários de tempo real: `normal`, `chuva_forte`, `enchente`, `recuperacao`.
Tudo é determinístico dado o `seed`.
"""
from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from area2_bigdata.tempo import FUSO_BR
from comum import territorio

CENARIOS = ("normal", "chuva_forte", "enchente", "recuperacao")

# Chuva média mensal aproximada de São Paulo (mm) — usada só como forma da sazonalidade.
CLIMATOLOGIA_MM = {1: 290, 2: 250, 3: 215, 4: 85, 5: 70, 6: 55, 7: 45, 8: 40, 9: 85, 10: 130, 11: 150, 12: 210}

# Volume efetivo (mm escoados no reservatório 2) que leva o rio do nível base ao transbordo.
VOLUME_TRANSBORDO_MM = 3.6
# Fração do escoamento que passa pela bacia lenta (sustenta a cheia por dias).
FRACAO_LENTA = 0.55

# Altura máxima (cm) que a lâmina sobe acima da cota de transbordo quando a água invade a várzea.
EXCESSO_MAX_CM = 90.0


def _fator_mes(mes: int) -> float:
    return CLIMATOLOGIA_MM[mes] / 150.0


def _fator_hora(hora: float) -> float:
    """Convecção concentrada no fim da tarde (pico ~16h30), com um piso pequeno no resto do dia."""
    return 0.12 + 2.2 * math.exp(-((hora - 16.5) ** 2) / (2 * 2.3**2))


def _seed_estacao(seed: int, estacao_id: str) -> int:
    return seed * 1_000_003 + zlib.crc32(estacao_id.encode())


@dataclass
class _Evento:
    restante_h: float
    intensidade: float
    decaimento: float  # fração por hora que a intensidade cai
    fatores: dict[str, float]  # "pegada" do evento: quanto da chuva cai em cada estação


class GeradorChuva:
    """Chuva (mm/h) por estação a partir de eventos regionais, avançado em passos de `dt_h` horas.

    Chuvas frontais cobrem todas as estações de forma parecida; células convectivas são locais
    (cada estação pode ficar de fora ou receber mais/menos chuva), o que espalha os transbordos.
    """

    P_CONVECTIVA_H = 0.012  # chance-base por hora de começar uma tempestade convectiva
    P_FRONTAL_H = 0.0028  # chance-base por hora de começar uma chuva frontal
    P_EXTREMO = 0.25  # fração das convectivas que vira evento extremo
    P_FORA_DA_CELULA = 0.35  # chance de uma estação não ser atingida por uma célula convectiva
    SIGMA_LOCAL = 0.45  # variação local da intensidade (lognormal)
    EXPOENTE_SAZONAL = 1.6  # convecção bem mais forte no verão do que no inverno seco
    EXTREMO_MM_H = (20.0, 60.0)  # faixa das tempestades extremas (as mais fracas só passam do alerta)

    def __init__(self, seed: int = 42, estacoes_ids: list[str] | None = None):
        self.rng = random.Random(seed)
        self.ids = list(estacoes_ids or [e["id"] for e in territorio.estacoes()])
        self.eventos: list[_Evento] = []

    def _pegada(self, local: bool) -> dict[str, float]:
        if not local:
            return {i: self.rng.uniform(0.8, 1.2) for i in self.ids}
        return {i: 0.0 if self.rng.random() < self.P_FORA_DA_CELULA else
                self.rng.lognormvariate(0, self.SIGMA_LOCAL) for i in self.ids}

    def passo(self, momento: datetime, dt_h: float) -> dict[str, float]:
        fm = _fator_mes(momento.month)
        hora = momento.hour + momento.minute / 60
        if self.rng.random() < self.P_CONVECTIVA_H * fm**self.EXPOENTE_SAZONAL * _fator_hora(hora) * dt_h:
            if self.rng.random() < self.P_EXTREMO:
                self.eventos.append(_Evento(self.rng.uniform(2, 4), self.rng.uniform(*self.EXTREMO_MM_H), 0.25,
                                            self._pegada(True)))
            else:
                intensidade = min(80.0, self.rng.lognormvariate(math.log(14), 0.6))
                self.eventos.append(_Evento(self.rng.uniform(1, 3), intensidade, 0.45, self._pegada(True)))
        if self.rng.random() < self.P_FRONTAL_H * fm * dt_h:
            self.eventos.append(_Evento(self.rng.uniform(4, 14), self.rng.uniform(0.8, 3.5), 0.0,
                                        self._pegada(False)))
        total = dict.fromkeys(self.ids, 0.0)
        vivos = []
        for ev in self.eventos:
            ruido = self.rng.uniform(0.7, 1.3)
            for i in self.ids:
                total[i] += ev.intensidade * ruido * ev.fatores[i]
            ev.intensidade *= (1 - ev.decaimento) ** dt_h
            ev.restante_h -= dt_h
            if ev.restante_h > 0 and ev.intensidade > 0.2:
                vivos.append(ev)
        self.eventos = vivos
        return total


class OndasMontante:
    """Ondas de cheia do Tietê vindas de montante (chuva na cabeceira, fora do território).

    Sobem em ~6–12 h e descem em ~1 dia; o pico (fração da amplitude base→transbordo) quase sempre
    fica entre a cota de alerta e a de transbordo — sozinha raramente transborda, mas somada a uma
    tempestade local pode transbordar.
    """

    P_ONDA_H = 0.0013
    PICO_FRAC = (0.5, 0.9)

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed + 13)
        self.ondas: list[list[float]] = []  # [idade_h, tempo_de_pico_h, pico_frac]

    def passo(self, momento: datetime, dt_h: float) -> float:
        if self.rng.random() < self.P_ONDA_H * _fator_mes(momento.month) ** 1.6 * dt_h:
            self.ondas.append([0.0, self.rng.uniform(6, 12), self.rng.uniform(*self.PICO_FRAC)])
        total = 0.0
        for onda in self.ondas:
            onda[0] += dt_h
            idade, pico_h, frac = onda
            total += frac * (idade / pico_h) * math.exp(1 - idade / pico_h)  # forma "gama": sobe e desce
        self.ondas = [o for o in self.ondas if o[0] < 8 * o[1]]
        return total


def chuva_do_cenario(cenario: str, rng: random.Random) -> float | None:
    """Chuva regional forçada pelo cenário (mm/h); None = segue a climatologia (cenário normal)."""
    if cenario == "chuva_forte":
        return max(0.0, rng.gauss(12, 5))
    if cenario == "enchente":
        return max(0.0, rng.gauss(80, 15))
    if cenario == "recuperacao":
        return 0.0
    return None


@dataclass
class EstacaoHidrologica:
    """Estado hidrológico de uma estação; `passo` avança o tempo e devolve a leitura dos sensores."""

    estacao: dict
    seed: int = 42
    umidade: float = 45.0
    lento: float = 0.0  # reservatório lento da bacia (mm): cheia acumulada de vários dias
    montante_cm: float = 0.0  # onda de cheia forçada pelos cenários (tempo real)
    onda_frac: float = 0.0  # onda natural de montante, em fração da amplitude base→transbordo
    bateria: float = 92.0
    rng: random.Random = field(init=False, repr=False)

    def __post_init__(self):
        self.rng = random.Random(_seed_estacao(self.seed, self.estacao["id"]))
        # Cascata de reservatórios lineares (Nash): o córrego responde mais rápido que a margem do Tietê.
        corrego = "ITAIM" in self.estacao["id"]
        self.constantes_h = (0.7, 1.0, 1.6) if corrego else (1.3, 1.8, 2.8)
        self.k_lento = 30.0 if corrego else 48.0
        self.reservatorios = [0.0] * len(self.constantes_h)
        self.base = float(self.estacao["nivel_base_cm"])
        self.amplitude = float(self.estacao["cota_transbordo_cm"]) - self.base
        self.ganho = self.amplitude / VOLUME_TRANSBORDO_MM
        self.fator_local = self.rng.uniform(0.9, 1.15)
        # O córrego sente pouco a cheia do Tietê; as margens sentem quase toda.
        self.fator_onda = 0.4 if corrego else self.rng.uniform(0.85, 1.05)

    def nivel_atual(self) -> float:
        bruto = (self.base + self.ganho * self.reservatorios[-1] + self.montante_cm
                 + self.onda_frac * self.fator_onda * self.amplitude)
        excesso = bruto - float(self.estacao["cota_transbordo_cm"])
        if excesso <= 0:
            return bruto
        # Acima da cota de transbordo a água se espalha pela várzea: o nível sobe cada vez menos.
        return float(self.estacao["cota_transbordo_cm"]) + excesso / (1 + excesso / EXCESSO_MAX_CM)

    @staticmethod
    def _reservatorio(armazenado: float, entrada: float, k: float, dt_h: float) -> tuple[float, float]:
        """Solução exata de dS/dt = entrada − S/k no passo; devolve (novo S, vazão média de saída)."""
        a = math.exp(-dt_h / k)
        novo = armazenado * a + entrada * k * (1 - a)
        return novo, (armazenado + entrada * dt_h - novo) / dt_h

    def passo(self, momento: datetime, chuva_local: float, dt_h: float, cenario: str = "normal",
              onda_frac: float = 0.0) -> dict:
        rng = self.rng
        self.onda_frac = onda_frac
        chuva = 0.0 if chuva_local <= 0 else chuva_local * self.fator_local * rng.lognormvariate(0, 0.2)
        chuva = min(chuva, 180.0)

        # Umidade do solo: infiltra com a chuva, seca devagar até ~28% sem ela.
        self.umidade += 0.35 * chuva * dt_h * (1 - self.umidade / 100)
        self.umidade -= (self.umidade - 28.0) * (1 - math.exp(-dt_h / 70.0))
        self.umidade = min(99.0, max(15.0, self.umidade))

        # Escoamento efetivo: solo encharcado escoa muito mais.
        coef = 0.08 + 0.80 * (self.umidade / 100) ** 2
        if cenario == "enchente":
            coef = max(coef, 0.75)
        escoamento = coef * chuva  # mm/h
        # Recuperação (demo): a vazante é acelerada para o rio baixar em poucos minutos de simulação.
        drenagem = 3.0 if cenario == "recuperacao" else 1.0
        self.lento, saida_lenta = self._reservatorio(self.lento, FRACAO_LENTA * escoamento,
                                                     self.k_lento / drenagem, dt_h)
        entrada = (1 - FRACAO_LENTA) * escoamento
        for i, k_h in enumerate(self.constantes_h):
            k = k_h / drenagem
            if i == len(self.constantes_h) - 1:
                entrada += saida_lenta  # a bacia lenta deságua no canal
            self.reservatorios[i], entrada = self._reservatorio(self.reservatorios[i], entrada, k, dt_h)
        # A várzea transborda e espalha a água: o armazenamento no canal tem um teto físico.
        teto = (self.amplitude + 1.5 * EXCESSO_MAX_CM) / self.ganho
        self.reservatorios = [min(s, teto) for s in self.reservatorios]
        self.lento = min(self.lento, 3 * teto)

        alvo, k_m = 0.0, 6.0
        if cenario == "enchente":
            alvo, k_m = 0.55 * self.amplitude, 1.2
        elif cenario == "recuperacao":
            k_m = 0.8
        self.montante_cm += (alvo - self.montante_cm) * (1 - math.exp(-dt_h / k_m))

        # Bateria: consumo contínuo + recarga solar de dia.
        hora = momento.hour
        self.bateria += (-0.18 + (0.55 if 7 <= hora < 17 else 0.0)) * dt_h
        self.bateria = min(100.0, max(20.0, self.bateria))

        nivel = self.nivel_atual() + rng.gauss(0, 0.8)
        nivel = min(599.0, max(0.0, nivel))
        return {
            "estacao_id": self.estacao["id"],
            "momento": momento,
            "nivel_cm": round(nivel, 1),
            "chuva_mm_h": round(max(0.0, chuva + (rng.gauss(0, 0.2) if chuva > 0 else 0.0)), 1),
            "umidade_solo_pct": round(min(100.0, max(0.0, self.umidade + rng.gauss(0, 0.5))), 1),
            "bateria_pct": int(round(self.bateria)),
        }


class ModeloRegional:
    """As 4 estações sob os mesmos eventos de chuva e ondas de montante; histórico e tempo real."""

    def __init__(self, inicio: datetime, seed: int = 42, cenario: str = "normal", estacoes: list[dict] | None = None):
        self.relogio = inicio if inicio.tzinfo else inicio.replace(tzinfo=FUSO_BR)
        self.seed = seed
        self.rng_cenario = random.Random(seed + 7)
        self.estacoes = [EstacaoHidrologica(e, seed) for e in (estacoes or territorio.estacoes())]
        self.chuva = GeradorChuva(seed, [est.estacao["id"] for est in self.estacoes])
        self.ondas = OndasMontante(seed)
        self.cenario = "normal"
        self.definir_cenario(cenario)

    def definir_cenario(self, nome: str) -> None:
        if nome not in CENARIOS:
            raise ValueError(f"cenário desconhecido: {nome} (use {', '.join(CENARIOS)})")
        self.cenario = nome

    def passo(self, dt_h: float = 1.0) -> list[dict]:
        """Avança `dt_h` horas e devolve uma leitura (sem assinatura) por estação, no novo relógio."""
        self.relogio = self.relogio + timedelta(hours=dt_h)
        chuva_clima = self.chuva.passo(self.relogio, dt_h)
        onda = self.ondas.passo(self.relogio, dt_h)
        forcada = chuva_do_cenario(self.cenario, self.rng_cenario)
        return [est.passo(self.relogio, chuva_clima[est.estacao["id"]] if forcada is None else forcada, dt_h,
                          self.cenario, onda) for est in self.estacoes]

    def aquecer(self, horas: int) -> None:
        """Roda o modelo sem guardar saída para o estado inicial não começar 'zerado'."""
        cenario = self.cenario
        self.cenario = "normal"
        self.relogio -= timedelta(hours=horas)
        for _ in range(horas):
            self.passo(1.0)
        self.cenario = cenario


def gerar_serie(inicio: datetime, fim: datetime, seed: int = 42, aquecimento_h: int = 720) -> list[dict]:
    """Série horária de `inicio` até `fim` (inclusive) para todas as estações."""
    modelo = ModeloRegional(inicio - timedelta(hours=1), seed=seed)
    modelo.aquecer(aquecimento_h)
    saida: list[dict] = []
    while modelo.relogio < fim:
        saida.extend(modelo.passo(1.0))
    return saida
