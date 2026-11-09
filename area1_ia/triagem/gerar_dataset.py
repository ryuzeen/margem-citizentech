"""Gera o dataset de TREINO `dados_rotulados.csv` combinando templates (relatos simulados).

Uso: python -m area1_ia.triagem.gerar_dataset

O conjunto de TESTE (`teste_manual.csv`) é escrito à mão e NÃO sai daqui: assim a avaliação mede
generalização para textos que o gerador nunca produziu.

Rubrica de gravidade (vale para o treino e para o teste):
  1 - informação, dúvida ou transtorno sem risco (pergunta sobre abrigo, poça na rua)
  2 - transtorno leve (rua alagada transitável a pé, água na soleira, falta de luz sem risco)
  3 - dano material / água dentro de casa / via intransitável / rachadura nova
  4 - risco à integridade: água alta dentro de casa, fio caído na água, muro cedendo, família ilhada
  5 - risco de vida imediato: pessoa arrastada, gente no telhado, desabamento com pessoas, choque
A gravidade descreve a SITUAÇÃO; vulneráveis entram na prioridade (agente de prioridade).
"""
from __future__ import annotations

import csv
import random
import re
from pathlib import Path

PASTA = Path(__file__).resolve().parent
ARQUIVO = PASTA / "dados_rotulados.csv"

# (frase, gravidade) por categoria
SITUACOES: dict[str, list[tuple[str, int]]] = {
    "agua_na_residencia": [
        ("tá entrando um pouco de água pela porta da cozinha", 2),
        ("a água já chegou no quintal e tá encostando na porta", 2),
        ("começou a molhar o chão da sala, a água tá vindo por baixo da porta", 2),
        ("a água tá na soleira da porta de casa", 2),
        ("o ralo do banheiro tá voltando água", 2),
        ("a água entrou em casa e já tá no tornozelo", 3),
        ("invadiu a casa toda, perdemos o sofá e a geladeira", 3),
        ("tem uns 20 cm de água dentro de casa", 3),
        ("a casa encheu de água, tá tudo molhado e estragado", 3),
        ("o esgoto voltou pelo ralo e a água suja tá subindo dentro de casa", 3),
        ("entrou água no quarto e molhou os colchões", 3),
        ("a cozinha alagou, a água tá no meio da canela", 3),
        ("a água já tá no joelho dentro de casa e não para de subir", 4),
        ("água na cintura aqui dentro, precisamos sair", 4),
        ("subiu muito rápido, a água tá batendo na altura da cama", 4),
        ("a gente subiu os móveis mas a água tá alta dentro de casa e continua subindo", 4),
        ("a água tá entrando com força pela janela", 4),
    ],
    "via_alagada": [
        ("a rua tá com umas poças grandes mas ainda dá pra passar", 1),
        ("a rua de casa alagou, carro baixo não passa", 2),
        ("alagou a avenida perto do ponto de ônibus", 2),
        ("o bueiro entupiu e a rua virou um rio", 2),
        ("o ônibus parou de passar porque a rua tá alagada", 2),
        ("a viela tá cheia de água e lama", 2),
        ("a rua tá com água na altura do joelho, ninguém consegue passar", 3),
        ("tem carro parado no meio da água na avenida", 3),
        ("enxurrada forte descendo a rua", 3),
        ("a água da rua tá chegando na porta das casas", 3),
        ("a ponte do córrego tá coberta de água", 3),
        ("a passagem debaixo da linha do trem encheu de água", 3),
        ("correnteza forte na rua arrastando lixo e moto", 4),
        ("um carro foi arrastado pela enxurrada, sem ninguém dentro", 4),
        ("tem um bueiro sem tampa na rua alagada e não dá pra ver", 4),
    ],
    "pessoa_ilhada": [
        ("estamos ilhados em casa, a rua tá toda tomada e não dá pra sair", 4),
        ("tem uma família presa no segundo andar, a água cercou a casa", 4),
        ("minha vizinha não consegue sair de casa, a água tá muito alta", 4),
        ("não tem como sair daqui, a água tomou tudo em volta", 4),
        ("tem gente presa no ônibus parado na água", 4),
        ("subimos no telhado, a água não para de subir", 5),
        ("tem um homem preso dentro do carro na água", 5),
        ("uma pessoa foi arrastada pela correnteza no córrego", 5),
        ("estamos presos no forro, a água tá quase no teto", 5),
        ("vi alguém se segurando num poste no meio da correnteza", 5),
        ("uma moça caiu no córrego e sumiu na água", 5),
    ],
    "risco_estrutural": [
        ("apareceu uma rachadura na parede depois da chuva", 3),
        ("o muro do vizinho tá inclinando pro nosso lado", 3),
        ("o barranco atrás de casa começou a ceder", 3),
        ("a calçada afundou na frente de casa", 3),
        ("o teto tá pingando e com uma mancha enorme", 2),
        ("a rachadura tá aumentando e a porta não fecha mais", 4),
        ("o muro tá estalando e vai cair a qualquer momento", 4),
        ("tá descendo terra do barranco em cima das casas", 4),
        ("o teto tá cedendo com o peso da água", 4),
        ("a laje tá estalando e caindo reboco", 4),
        ("o muro desabou em cima da casa do lado", 5),
        ("a casa desabou e tem gente lá dentro", 5),
        ("desmoronou o barranco e soterrou um barraco", 5),
    ],
    "falta_energia": [
        ("a luz fica piscando desde que começou a chuva", 1),
        ("acabou a luz aqui na rua desde cedo", 2),
        ("tá sem energia no bairro todo", 2),
        ("caiu a energia e a geladeira tá desligada faz horas", 2),
        ("estamos sem luz há mais de doze horas", 2),
        ("o transformador do poste estourou e acabou a luz", 3),
        ("tem um fio caído na água aqui na rua", 4),
        ("o poste caiu e o fio tá soltando faísca", 4),
        ("o relógio de luz tá dentro da água", 4),
        ("tomada dentro de casa ficou debaixo da água e tá dando choque", 4),
        ("um rapaz levou choque encostando no portão com a rua alagada", 5),
    ],
    "outro": [
        ("onde fica o abrigo mais perto?", 1),
        ("como faço pra me cadastrar pra receber alerta?", 1),
        ("vai chover forte hoje à noite?", 1),
        ("obrigado pelo aviso de ontem", 1),
        ("quero doar roupa e comida, onde eu levo?", 1),
        ("a escola vai ter aula amanhã com essa chuva?", 1),
        ("o rio tá subindo? tô preocupado", 1),
        ("qual o telefone da defesa civil?", 1),
        ("a coleta de lixo não passou e tá tudo acumulado", 1),
        ("tem muito rato e lixo depois da enchente", 2),
        ("a água da torneira tá saindo barrenta", 2),
        ("perdi meus documentos na enchente, como tiro de novo?", 1),
        ("posso voltar pra casa já? a água baixou", 2),
        ("tô com febre e dor na batata da perna depois de andar na água da enchente", 3),
        ("a casa ficou cheia de lama, como limpo sem pegar doença?", 2),
        ("tem cobra e escorpião aparecendo depois da chuva", 2),
    ],
}

ABERTURAS = ["", "", "", "socorro", "boa noite", "bom dia", "boa tarde", "gente", "oi", "pelo amor de Deus",
             "urgente", "alô", "Defesa Civil,", "ei", "por favor", "moço", "olá"]
LOCAIS = ["", "", "", "aqui no Jardim Pantanal", "na rua de trás do campinho", "perto da escola",
          "aqui na Vila Itaim", "no Jardim Romano", "perto do córrego", "na viela", "no Jd Helena",
          "perto da linha do trem", "na rua 3", "do lado do mercadinho", "perto da igreja",
          "na rua da padaria", "no fim da rua sem saída", "lá na baixada"]
FECHAMENTOS = ["", "", "", "pfv", "mandem ajuda", "o que eu faço?", "alguém ajuda", "obrigado", "rápido",
               "tô com medo", "por favor venham", "aguardo", "help", "Deus ajude"]

# (frase, vulneráveis)
VULNERAVEIS: list[tuple[str, list[str]]] = [
    ("minha mãe de 82 anos mora comigo", ["idoso"]),
    ("tem uma idosa sozinha na casa", ["idoso"]),
    ("minha vó tá aqui com a gente", ["idoso"]),
    ("tem um casal de velhinhos na casa do lado", ["idoso"]),
    ("meu pai tem 77 anos e anda devagar", ["idoso"]),
    ("meu irmão é cadeirante", ["pcd"]),
    ("tem um rapaz de cadeira de rodas aqui", ["pcd"]),
    ("meu filho é autista e tá muito agitado", ["pcd"]),
    ("minha tia é cega", ["pcd"]),
    ("meu marido anda de muleta", ["pcd"]),
    ("tô com duas crianças pequenas", ["crianca"]),
    ("tem um bebê de 3 meses aqui", ["crianca"]),
    ("tô sozinha com meus filhos pequenos", ["crianca"]),
    ("tem várias crianças na casa", ["crianca"]),
    ("meu neném tá dormindo", ["crianca"]),
    ("minha esposa tá grávida de 8 meses", ["gestante"]),
    ("tô grávida", ["gestante"]),
    ("tem uma gestante aqui", ["gestante"]),
    ("meu avô é acamado", ["idoso", "acamado"]),
    ("minha tia fica de cama, não levanta", ["acamado"]),
    ("meu pai usa oxigênio e não sai da cama", ["acamado"]),
    ("tem uma senhora acamada no quarto", ["idoso", "acamado"]),
    ("minha vó é cadeirante", ["idoso", "pcd"]),
    ("tô grávida e com uma criança de 2 anos", ["gestante", "crianca"]),
    ("não tem criança nem idoso aqui, só adulto", []),
]

ABREVIACOES = [
    (r"\bvocê\b", "vc"), (r"\bque\b", "q"), (r"\bestá\b", "ta"), (r"\btá\b", "ta"), (r"\bpara\b", "pra"),
    (r"\bmuito\b", "mt"), (r"\bporque\b", "pq"), (r"\btambém\b", "tb"), (r"\bnão\b", "n"),
    (r"\baqui\b", "aki"), (r"\bgente\b", "gnt"), (r"\bpor favor\b", "pf"), (r"\bcasa\b", "ksa"),
    (r"\bágua\b", "agua"), (r"\btô\b", "to"), (r"\bdepois\b", "dps"), (r"\bhoje\b", "hj"),
]
PREENCHIMENTOS = ["é", "tipo", "né", "então", "assim", "olha", "moço", "é é"]


def _sem_acento(texto: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def _erro_digitacao(texto: str, rng: random.Random) -> str:
    palavras = texto.split()
    for _ in range(rng.randint(1, 2)):
        idx = [i for i, p in enumerate(palavras) if len(p) > 4]
        if not idx:
            break
        i = rng.choice(idx)
        p = palavras[i]
        j = rng.randint(1, len(p) - 2)
        operacao = rng.choice(["troca", "apaga", "duplica"])
        if operacao == "troca":
            p = p[:j] + p[j + 1] + p[j] + p[j + 2 :]
        elif operacao == "apaga":
            p = p[:j] + p[j + 1 :]
        else:
            p = p[:j] + p[j] + p[j:]
        palavras[i] = p
    return " ".join(palavras)


def _whatsapp(texto: str, rng: random.Random) -> str:
    texto = texto.lower()
    for padrao, troca in ABREVIACOES:
        if rng.random() < 0.6:
            texto = re.sub(padrao, troca, texto)
    if rng.random() < 0.5:
        texto = _sem_acento(texto)
    texto = texto.replace(".", "").replace(",", "")
    if rng.random() < 0.3:
        texto += rng.choice(["!!!", "!!", "??", " 😭", " 🙏", " socorrooo"])
    return texto


def _audio(texto: str, rng: random.Random) -> str:
    palavras = re.sub(r"[.,!?;]", "", texto.lower()).split()
    saida = []
    for p in palavras:
        if rng.random() < 0.12:
            saida.append(rng.choice(PREENCHIMENTOS))
        saida.append(p)
        if rng.random() < 0.05:
            saida.append(p)
    return "[áudio transcrito] " + " ".join(saida) if rng.random() < 0.3 else " ".join(saida)


def _montar(categoria: str, frase: str, rng: random.Random) -> tuple[str, list[str]]:
    partes = []
    abertura = rng.choice(ABERTURAS)
    if abertura:
        partes.append(abertura)
    local = rng.choice(LOCAIS)
    if local and rng.random() < 0.5:
        partes.append(f"{local} {frase}")
    elif local:
        partes.append(f"{frase} {local}")
    else:
        partes.append(frase)
    vulneraveis: list[str] = []
    if categoria != "outro" and rng.random() < 0.4 or categoria == "outro" and rng.random() < 0.1:
        frase_v, vulneraveis = rng.choice(VULNERAVEIS)
        partes.append(frase_v)
    fechamento = rng.choice(FECHAMENTOS)
    if fechamento:
        partes.append(fechamento)
    texto = ", ".join(partes)
    return texto[0].upper() + texto[1:], list(vulneraveis)


def _estilizar(texto: str, rng: random.Random) -> str:
    estilo = rng.random()
    if estilo < 0.35:
        texto = _whatsapp(texto, rng)
    elif estilo < 0.5:
        texto = _audio(texto, rng)
    elif estilo < 0.55:
        texto = _sem_acento(texto).upper()
    if rng.random() < 0.3:
        texto = _erro_digitacao(texto, rng)
    return texto


def gerar(por_frase: int = 7, semente: int = 2026) -> list[dict]:
    rng = random.Random(semente)
    linhas: list[dict] = []
    vistos: set[str] = set()
    for categoria, frases in SITUACOES.items():
        for frase, gravidade in frases:
            for _ in range(por_frase):
                texto, vulneraveis = _montar(categoria, frase, rng)
                texto = _estilizar(texto, rng)
                if texto in vistos:
                    continue
                vistos.add(texto)
                linhas.append({
                    "texto": texto,
                    "categoria": categoria,
                    "gravidade": gravidade,
                    "vulneraveis": "|".join(vulneraveis),
                })
    rng.shuffle(linhas)
    return linhas


def salvar(linhas: list[dict], caminho: Path = ARQUIVO) -> Path:
    with open(caminho, "w", encoding="utf-8", newline="") as arq:
        escritor = csv.DictWriter(arq, fieldnames=["texto", "categoria", "gravidade", "vulneraveis"])
        escritor.writeheader()
        escritor.writerows(linhas)
    return caminho


if __name__ == "__main__":
    linhas = gerar()
    caminho = salvar(linhas)
    print(f"{len(linhas)} relatos de treino gravados em {caminho}")
