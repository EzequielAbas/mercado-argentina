"""
fuente_byma.py — Conector para datos de BYMA (Bolsas y Mercados Argentinos)

Trae precios en tiempo real de bonos y LEBACs desde la API publica de BYMA.
Calcula TIR simple (diaria, nominal anual, efectiva anual, TNA).

Adaptado de trading_bcra (github) para integrarse con el reporte de cartera.

Dependencias: requests, pandas, numpy (ya instaladas)
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime

URL_BONDS = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/public-bonds"
URL_LEBACS = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/lebacs"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

BASE_COLS = [
    "symbol", "trade", "bidPrice", "offerPrice",
    "previousSettlementPrice", "volume", "tradeVolume",
    "maturityDate", "denominationCcy", "market", "tradeHour",
]

TIMEOUT = 12

_cache = {"df": None, "ts": None}


def _normalizar_df(df: pd.DataFrame) -> pd.DataFrame:
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None
    return df[BASE_COLS].copy()


def _fetch(url: str, payload: dict) -> pd.DataFrame:
    try:
        resp = requests.post(url, headers=HEADERS, json=payload,
                             timeout=TIMEOUT, verify=True)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return pd.DataFrame(columns=BASE_COLS)
        return _normalizar_df(pd.DataFrame(data))
    except Exception:
        return pd.DataFrame(columns=BASE_COLS)


def obtener_precios_byma(usar_cache: bool = True) -> pd.DataFrame:
    """
    Trae precios de bonos (T0 y T1) y LEBACs desde BYMA.
    Devuelve DataFrame con columnas: symbol, precio_actual, maturityDate,
    denominationCcy, type, settlement.
    """
    if usar_cache and _cache["df"] is not None:
        return _cache["df"].copy()

    partes = []

    df_t0 = _fetch(URL_BONDS, {"T0": True, "T1": False})
    if not df_t0.empty:
        df_t0["settlement"] = "T0"
        df_t0["type"] = "bond"
        partes.append(df_t0)

    df_t1 = _fetch(URL_BONDS, {"T0": False, "T1": True})
    if not df_t1.empty:
        df_t1["settlement"] = "T1"
        df_t1["type"] = "bond"
        partes.append(df_t1)

    df_leb = _fetch(URL_LEBACS, {"T0": True, "T1": True})
    if not df_leb.empty:
        df_leb["settlement"] = "T0/T1"
        df_leb["type"] = "lebac"
        partes.append(df_leb)

    if not partes:
        return pd.DataFrame()

    df = pd.concat(partes, ignore_index=True)
    df = _consolidar_precio(df)

    # Deduplicar: quedarse con T1 (24hs) si hay duplicados
    df["_prio"] = df["settlement"].map({"T1": 0, "T0": 1, "T0/T1": 2}).fillna(3)
    df = df.sort_values(["symbol", "_prio"]).drop_duplicates(subset=["symbol"], keep="first")
    df = df.drop(columns=["_prio"])

    _cache["df"] = df.copy()
    _cache["ts"] = datetime.now()
    return df


def _consolidar_precio(df: pd.DataFrame) -> pd.DataFrame:
    """Prioriza: offerPrice > bidPrice > previousSettlementPrice."""
    df["precio_actual"] = pd.to_numeric(df["offerPrice"], errors="coerce").fillna(0)
    mask_cero = df["precio_actual"] == 0
    df.loc[mask_cero, "precio_actual"] = pd.to_numeric(df.loc[mask_cero, "bidPrice"], errors="coerce").fillna(0)
    mask_cero = df["precio_actual"] == 0
    df.loc[mask_cero, "precio_actual"] = pd.to_numeric(df.loc[mask_cero, "previousSettlementPrice"], errors="coerce").fillna(0)
    return df


def ajustar_escala(precio: float) -> tuple:
    """
    BYMA reporta precios con escalas distintas segun el instrumento.
    Algunos vienen por VN 100, otros por VN 1000 o 10000.
    Devuelve (precio_ajustado, factor_escala).
    """
    if pd.isna(precio) or precio <= 0:
        return np.nan, np.nan
    if precio > 100_000:
        return precio / 10_000, 10_000
    elif precio > 10_000:
        return precio / 1_000, 1_000
    elif precio > 1_000:
        return precio / 100, 100
    return precio, 1


def calcular_tir_simple(precio_actual: float, valor_final: float,
                        dias_al_vto: int) -> dict | None:
    """
    Calcula TIR simple para un instrumento de renta fija.

    La TIR (Tasa Interna de Retorno) mide el rendimiento anualizado
    de comprar a precio_actual y cobrar valor_final en N dias.

    Formula:
      TIR diaria = (valor_final / precio)^(1/dias) - 1
      TIR anual nominal = TIR_diaria * 365
      TIR anual efectiva = (1 + TIR_diaria)^365 - 1
      TNA = (valor_final/precio - 1) * (365/dias)
    """
    if (not precio_actual or precio_actual <= 0
            or not valor_final or valor_final <= 0
            or not dias_al_vto or dias_al_vto <= 0):
        return None

    try:
        tir_d = (valor_final / precio_actual) ** (1 / dias_al_vto) - 1
        if not (-0.5 <= tir_d <= 0.5):
            return None
        tir_nom = tir_d * 365
        tir_ef = (1 + tir_d) ** 365 - 1
        tna = (valor_final / precio_actual - 1) * (365 / dias_al_vto)
        return {
            "tir_diaria": round(tir_d, 8),
            "tir_anual_nominal": round(tir_nom, 4),
            "tir_anual_efectiva": round(tir_ef, 4),
            "tna": round(tna, 4),
        }
    except (ZeroDivisionError, ValueError, OverflowError):
        return None


def obtener_precio_ticker(ticker: str) -> dict | None:
    """Busca un ticker especifico en los datos de BYMA."""
    df = obtener_precios_byma()
    if df.empty:
        return None
    ticker_up = ticker.strip().upper()
    fila = df[df["symbol"].str.upper().str.strip() == ticker_up]
    if fila.empty:
        return None
    r = fila.iloc[0]
    return {
        "symbol": r.get("symbol"),
        "precio_actual": r.get("precio_actual"),
        "maturityDate": r.get("maturityDate"),
        "denominationCcy": r.get("denominationCcy"),
        "settlement": r.get("settlement"),
    }


if __name__ == "__main__":
    print("=== Test fuente_byma.py ===")
    df = obtener_precios_byma(usar_cache=False)
    if df.empty:
        print("No se pudo conectar a BYMA (puede estar fuera de horario).")
    else:
        print(f"Instrumentos obtenidos: {len(df)}")
        bonos = df[df["type"] == "bond"]
        lebacs = df[df["type"] == "lebac"]
        print(f"  Bonos: {len(bonos)}  |  LEBACs: {len(lebacs)}")

        # Mostrar primeros 5 con precio
        con_precio = df[df["precio_actual"] > 0].head(5)
        for _, r in con_precio.iterrows():
            print(f"  {r['symbol']:10s} ${r['precio_actual']:>12,.2f}  vto: {r['maturityDate']}")

        # Test TIR simple
        tir = calcular_tir_simple(precio_actual=95, valor_final=100, dias_al_vto=180)
        print(f"\nTest TIR (comprar a $95, cobrar $100 en 180 dias):")
        if tir:
            print(f"  TIR nominal anual: {tir['tir_anual_nominal']:.2%}")
            print(f"  TIR efectiva anual: {tir['tir_anual_efectiva']:.2%}")
            print(f"  TNA: {tir['tna']:.2%}")
