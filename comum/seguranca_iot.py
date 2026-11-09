"""Assinatura HMAC-SHA256 das leituras IoT (mesma regra do firmware ESP32)."""
from __future__ import annotations

import hashlib
import hmac


def mensagem_canonica(leitura: dict) -> str:
    return (
        f"{leitura['estacao_id']}|{leitura['ts']}|{int(leitura['seq'])}|"
        f"{float(leitura['nivel_cm']):.1f}|{float(leitura['chuva_mm_h']):.1f}|"
        f"{float(leitura['umidade_solo_pct']):.1f}"
    )


def assinar(leitura: dict, token: str) -> str:
    return hmac.new(token.encode(), mensagem_canonica(leitura).encode(), hashlib.sha256).hexdigest()


def assinatura_valida(leitura: dict, token: str | None) -> bool:
    if not token or not leitura.get("sig"):
        return False
    return hmac.compare_digest(assinar(leitura, token), str(leitura["sig"]))
