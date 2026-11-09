"""Copia os CSVs da camada refinada (dados/data_lake/refinada/powerbi) para area2_bigdata/powerbi/dados.

Uso (na raiz do repositório):  .venv/Scripts/python area2_bigdata/powerbi/atualizar_dados.py
Depois, no Power BI Desktop: Página Inicial > Atualizar.
"""
import shutil
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ORIGEM = AQUI.parents[1] / "dados" / "data_lake" / "refinada" / "powerbi"
DESTINO = AQUI / "dados"


def main() -> int:
    csvs = sorted(ORIGEM.glob("*.csv"))
    if not csvs:
        print(f"Nenhum CSV em {ORIGEM}. Rode o pipeline antes (python iniciar.py ou o processamento da área 2).")
        return 1
    DESTINO.mkdir(exist_ok=True)
    for csv in csvs:
        shutil.copy2(csv, DESTINO / csv.name)
        linhas = sum(1 for _ in csv.open(encoding="utf-8")) - 1
        print(f"{csv.name:<24} {linhas:>7} linhas")
    print(f"{len(csvs)} arquivos copiados para {DESTINO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
