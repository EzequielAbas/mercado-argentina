"""
=============================================================
  ANÁLISIS TÉCNICO — módulo para Cartera Inversor v4
  Ezequiel | junio 2026

  Calcula indicadores técnicos REALES sobre series históricas:
    - RSI (14)         → sobrecompra / sobreventa
    - EMA 20 / EMA 50  → tendencia y cruces
    - SMA 20 / SMA 50  → medias simples de referencia
    - Volumen + media de volumen → confirmación

  FUENTES DE HISTÓRICO (en orden de preferencia):
    1. IOL API   → serie histórica de bonos/CEDEARs locales (AO27, XLP)
    2. yfinance  → respaldo para tickers de EEUU (XLP en NYSE)

  IMPORTANTE: este módulo SOLO calcula y describe. No ejecuta
  ni sugiere operar de forma automática. Es para INFORMAR tu
  decisión manual.

  Dependencias:
    pip install pandas numpy
    pip install yfinance        (opcional, respaldo XLP)

  Uso standalone (para probar):
    python analisis_tecnico.py
=============================================================
"""

import datetime
from pathlib import Path

# ── Dependencias núcleo ───────────────────────────────────
try:
    import pandas as pd
    import numpy as np
except ImportError:
    raise SystemExit("[!] Instalar: pip install pandas numpy")

# ── yfinance es opcional (respaldo) ───────────────────────
try:
    import yfinance as yf
    _YF = True
except ImportError:
    _YF = False


# ═══════════════════════════════════════════════════════════
#  CÁLCULO DE INDICADORES (sin librerías externas de TA)
#  Implementados a mano para que entiendas qué hace cada uno.
# ═══════════════════════════════════════════════════════════

def ema(serie: pd.Series, periodo: int) -> pd.Series:
    """Media Móvil Exponencial. Da más peso a los datos recientes."""
    return serie.ewm(span=periodo, adjust=False).mean()


def sma(serie: pd.Series, periodo: int) -> pd.Series:
    """Media Móvil Simple. Promedio aritmético de los últimos N períodos."""
    return serie.rolling(window=periodo).mean()


def rsi(serie: pd.Series, periodo: int = 14) -> pd.Series:
    """
    Índice de Fuerza Relativa (RSI).
    Mide la velocidad y magnitud de los cambios de precio.
      RSI > 70 → sobrecompra (posible techo)
      RSI < 30 → sobreventa  (posible piso)
    Usa el suavizado de Wilder (EMA con alpha = 1/periodo).
    """
    delta = serie.diff()
    ganancia = delta.where(delta > 0, 0.0)
    perdida = -delta.where(delta < 0, 0.0)

    avg_gan = ganancia.ewm(alpha=1 / periodo, adjust=False).mean()
    avg_per = perdida.ewm(alpha=1 / periodo, adjust=False).mean()

    rs = avg_gan / avg_per.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))
    # Si no hubo pérdidas, RSI = 100; si no hubo ganancias, RSI = 0
    rsi_val = rsi_val.fillna(100).where(avg_per != 0, 100)
    return rsi_val


# ═══════════════════════════════════════════════════════════
#  OBTENCIÓN DE HISTÓRICO — IOL (primario)
# ═══════════════════════════════════════════════════════════

def historico_iol(iol_get_fn, simbolo: str, mercado: str = "bCBA",
                  dias: int = 120) -> pd.DataFrame | None:
    """
    Trae la serie histórica diaria desde IOL.
    `iol_get_fn` es la función iol_get() del script principal
    (ya autenticada) — se la pasamos para reutilizar el token.

    Endpoint IOL:
      /api/v2/{mercado}/Titulos/{simbolo}/Cotizacion/seriehistorica/
              {desde}/{hasta}/{ajustada}

    Devuelve DataFrame con columnas: date, open, high, low, close, volume
    """
    hasta = datetime.date.today()
    desde = hasta - datetime.timedelta(days=dias)
    path = (f"/api/v2/{mercado}/Titulos/{simbolo}/Cotizacion/seriehistorica/"
            f"{desde.isoformat()}/{hasta.isoformat()}/SinAjustar")

    data = iol_get_fn(path)
    if not data or not isinstance(data, list) or len(data) < 5:
        return None

    filas = []
    for d in data:
        cierre = d.get("ultimoPrecio") or d.get("cierreAnterior")
        if cierre is None:
            continue
        filas.append({
            "date":   (d.get("fechaHora") or "")[:10],
            "open":   d.get("apertura") or cierre,
            "high":   d.get("maximo") or cierre,
            "low":    d.get("minimo") or cierre,
            "close":  cierre,
            "volume": d.get("volumenNominal") or d.get("montoOperado") or 0,
        })
    if len(filas) < 5:
        return None

    df = pd.DataFrame(filas)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# ═══════════════════════════════════════════════════════════
#  OBTENCIÓN DE HISTÓRICO — yfinance (respaldo XLP)
# ═══════════════════════════════════════════════════════════

def historico_yfinance(ticker: str = "XLP", dias: int = 120) -> pd.DataFrame | None:
    """
    Respaldo para tickers de EEUU. XLP cotiza en NYSE Arca.
    Solo se usa si IOL no devuelve serie y yfinance está instalado.
    """
    if not _YF:
        return None
    try:
        periodo = f"{max(dias, 60)}d"
        raw = yf.Ticker(ticker).history(period=periodo, interval="1d")
        if raw is None or raw.empty:
            return None
        df = raw.reset_index().rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        return df[["date", "open", "high", "low", "close", "volume"]]
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
#  ANÁLISIS COMPLETO DE UN INSTRUMENTO
# ═══════════════════════════════════════════════════════════

def analizar(df: pd.DataFrame) -> dict | None:
    """
    Recibe un DataFrame OHLCV y devuelve un dict con todos los
    indicadores + una lectura textual en castellano.
    """
    if df is None or len(df) < 20:
        return None

    close = df["close"]
    vol = df["volume"]

    df = df.copy()
    df["ema20"] = ema(close, 20)
    df["ema50"] = ema(close, 50)
    df["sma20"] = sma(close, 20)
    df["sma50"] = sma(close, 50)
    df["rsi14"] = rsi(close, 14)
    df["vol_ma20"] = sma(vol, 20)

    ult = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else ult

    precio = float(ult["close"])
    rsi_v = float(ult["rsi14"]) if pd.notna(ult["rsi14"]) else None
    ema20 = float(ult["ema20"]) if pd.notna(ult["ema20"]) else None
    ema50 = float(ult["ema50"]) if pd.notna(ult["ema50"]) else None
    vol_v = float(ult["volume"]) if pd.notna(ult["volume"]) else 0.0
    vol_ma = float(ult["vol_ma20"]) if pd.notna(ult["vol_ma20"]) else None

    # ── Detección de cruce EMA20/EMA50 ───────────────────
    cruce = "sin cruce"
    if ema20 and ema50 and pd.notna(prev["ema20"]) and pd.notna(prev["ema50"]):
        antes = prev["ema20"] - prev["ema50"]
        ahora = ema20 - ema50
        if antes <= 0 < ahora:
            cruce = "cruce alcista (golden) reciente"
        elif antes >= 0 > ahora:
            cruce = "cruce bajista (death) reciente"
        elif ahora > 0:
            cruce = "EMA20 sobre EMA50 (tendencia alcista)"
        else:
            cruce = "EMA20 bajo EMA50 (tendencia bajista)"

    # ── Lectura RSI ──────────────────────────────────────
    if rsi_v is None:
        rsi_txt = "sin datos"
    elif rsi_v >= 70:
        rsi_txt = "sobrecompra"
    elif rsi_v <= 30:
        rsi_txt = "sobreventa"
    elif rsi_v >= 55:
        rsi_txt = "impulso alcista"
    elif rsi_v <= 45:
        rsi_txt = "impulso bajista"
    else:
        rsi_txt = "neutral"

    # ── Lectura volumen ──────────────────────────────────
    vol_txt = "sin datos"
    vol_ratio = None
    if vol_ma and vol_ma > 0:
        vol_ratio = vol_v / vol_ma
        if vol_ratio >= 1.5:
            vol_txt = "volumen alto (confirma movimiento)"
        elif vol_ratio <= 0.6:
            vol_txt = "volumen bajo (movimiento débil)"
        else:
            vol_txt = "volumen normal"

    return {
        "precio":     round(precio, 2),
        "rsi":        round(rsi_v, 1) if rsi_v is not None else None,
        "rsi_lectura": rsi_txt,
        "ema20":      round(ema20, 2) if ema20 else None,
        "ema50":      round(ema50, 2) if ema50 else None,
        "cruce":      cruce,
        "volumen":    round(vol_v, 0),
        "vol_ma20":   round(vol_ma, 0) if vol_ma else None,
        "vol_ratio":  round(vol_ratio, 2) if vol_ratio else None,
        "vol_lectura": vol_txt,
        "n_datos":    len(df),
        "fecha_ult":  str(ult["date"])[:10],
        # serie reducida para mini-gráfico en el HTML (últimos 30 cierres)
        "sparkline":  [round(float(x), 2) for x in close.tail(30).tolist()],
    }


# ═══════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA QUE USA EL SCRIPT PRINCIPAL
# ═══════════════════════════════════════════════════════════

def analizar_instrumento(iol_get_fn, simbolo: str, mercado: str = "bCBA",
                         ticker_yf: str | None = None,
                         usar_rava: bool = True) -> dict | None:
    """
    Orquesta las fuentes de histórico y devuelve el análisis listo
    para inyectar en el reporte.

    Orden de preferencia:
      1. Rava (histórico embebido en /perfil) — instrumentos argentinos
      2. IOL (API autenticada)
      3. yfinance (para tickers de EEUU como XLP)

    Devuelve dict con clave "fuente" indicando de dónde salieron los datos.
    """
    df = None
    fuente = None

    if usar_rava:
        try:
            import fuente_rava as _rava
            df = _rava.get_perfil_historico(simbolo)
            if df is not None and len(df) >= 30:
                fuente = "Rava"
            else:
                df = None
        except Exception:
            df = None

    if df is None:
        df = historico_iol(iol_get_fn, simbolo, mercado)
        if df is not None:
            fuente = "IOL"

    if df is None and ticker_yf:
        df = historico_yfinance(ticker_yf)
        if df is not None:
            fuente = "yfinance"

    res = analizar(df)
    if res:
        res["fuente"] = fuente
        res["simbolo"] = simbolo
    return res


# ═══════════════════════════════════════════════════════════
#  PRUEBA STANDALONE (sin IOL, usa yfinance con XLP)
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Prueba standalone de analisis_tecnico.py")
    print("=" * 50)
    if not _YF:
        print("yfinance no instalado — instalá con: pip install yfinance")
        raise SystemExit(0)

    df = historico_yfinance("XLP", dias=120)
    if df is None:
        print("No se pudo traer histórico de XLP")
        raise SystemExit(0)

    res = analizar(df)
    print(f"\nXLP — análisis técnico ({res['n_datos']} ruedas)")
    print(f"  Precio:   ${res['precio']}")
    print(f"  RSI(14):  {res['rsi']}  → {res['rsi_lectura']}")
    print(f"  EMA20:    ${res['ema20']}")
    print(f"  EMA50:    ${res['ema50']}")
    print(f"  Cruce:    {res['cruce']}")
    print(f"  Volumen:  {res['volumen']:,.0f}  ({res['vol_lectura']})")
