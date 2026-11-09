"""Utilitários de data/hora no fuso fixo do projeto (-03:00)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

FUSO_BR = timezone(timedelta(hours=-3))


def agora() -> datetime:
    return datetime.now(FUSO_BR)


def para_datetime(valor) -> datetime | None:
    """Converte str ISO 8601 / datetime em datetime com fuso (-03:00 se vier sem fuso)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        dt = valor
    else:
        texto = str(valor).strip().replace("Z", "+00:00")
        if len(texto) == 10:
            texto += "T00:00:00"
        dt = datetime.fromisoformat(texto)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=FUSO_BR)
    return dt.astimezone(FUSO_BR)


def iso(dt: datetime) -> str:
    """ISO 8601 com segundos e fuso -03:00 (formato do contrato §4)."""
    return dt.astimezone(FUSO_BR).replace(microsecond=0).isoformat()


def normalizar_fusos(df):
    """Colunas datetime com fuso lidas do parquet (pytz.FixedOffset) -> mesmo objeto de fuso FUSO_BR."""
    import pandas as pd

    for col in df.columns:
        if isinstance(df[col].dtype, pd.DatetimeTZDtype):
            df[col] = df[col].dt.tz_convert(FUSO_BR)
    return df
