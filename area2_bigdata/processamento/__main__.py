"""CLI: python -m area2_bigdata.processamento [--completo]"""
from __future__ import annotations

import argparse
import json

from area2_bigdata.processamento import processar


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Processa o data lake do Margem (bruta -> confiavel -> refinada)")
    parser.add_argument("--completo", action="store_true", help="ignora o estado incremental e reconstrói tudo")
    args = parser.parse_args(argv)
    print(json.dumps(processar(completo=args.completo), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
