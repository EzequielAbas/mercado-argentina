"""
=============================================================
  INDICADORES TÉCNICOS AVANZADOS — Cartera Inversor v6
  Ezequiel | junio 2026

  Calcula sobre una serie OHLCV diaria:
    - SMA / EMA (varios períodos)
    - RSI (14)
    - MACD (12,26,9)
    - Estocástico (14,3,3)
    - ATR (14) — volatilidad
    - DM / ADX (+DI, -DI) (14) — fuerza de tendencia
    - VWAP aproximado (rolling, con cierres diarios)
    - Fibonacci (retrocesos desde swing high/low)
    - Bollinger Bands (20, 2σ)

  Luego combina todo en un SCORE 0-100 y una señal global.

  NOTA sobre limitaciones de datos diarios:
    - VWAP real requiere datos intradiarios (precio+volumen tick).
      Acá se aproxima con typical price diario ponderado por volumen.
    - "Order flow / Under flow" NO es calculable sin libro de órdenes
      (bid/ask por nivel), que ninguna fuente gratuita expone.

  Todo implementado a mano con pandas/numpy (sin librerías de TA externas)
  para que sea transparente y auditable.

  Dependencias: pandas, numpy
=============================================================
"""

import pandas as pd
import numpy as np


# ─────────────────────────────────────────────────────────────
#  INDICADORES INDIVIDUALES
# ─────────────────────────────────────────────────────────────

def sma(serie: pd.Series, periodo: int) -> pd.Series:
    return serie.rolling(window=periodo).mean()


def ema(serie: pd.Series, periodo: int) -> pd.Series:
    return serie.ewm(span=periodo, adjust=False).mean()


def rsi(serie: pd.Series, periodo: int = 14) -> pd.Series:
    delta = serie.diff()
    gan = delta.where(delta > 0, 0.0)
    per = -delta.where(delta < 0, 0.0)
    avg_gan = gan.ewm(alpha=1/periodo, adjust=False).mean()
    avg_per = per.ewm(alpha=1/periodo, adjust=False).mean()
    rs = avg_gan / avg_per.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(100).where(avg_per != 0, 100)


def macd(serie: pd.Series, rapida=12, lenta=26, signal=9) -> dict:
    ema_rap = ema(serie, rapida)
    ema_len = ema(serie, lenta)
    linea = ema_rap - ema_len
    senal = ema(linea, signal)
    histograma = linea - senal
    return {"macd": linea, "signal": senal, "hist": histograma}


def estocastico(df: pd.DataFrame, k=14, d=3, suavizado=3) -> dict:
    bajo_min = df["low"].rolling(window=k).min()
    alto_max = df["high"].rolling(window=k).max()
    k_raw = 100 * (df["close"] - bajo_min) / (alto_max - bajo_min).replace(0, np.nan)
    k_suave = k_raw.rolling(window=suavizado).mean()
    d_linea = k_suave.rolling(window=d).mean()
    return {"k": k_suave, "d": d_linea}


def atr(df: pd.DataFrame, periodo: int = 14) -> pd.Series:
    """Average True Range — mide volatilidad absoluta."""
    h_l = df["high"] - df["low"]
    h_pc = (df["high"] - df["close"].shift()).abs()
    l_pc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
    return tr.ewm(alpha=1/periodo, adjust=False).mean()


def adx_dm(df: pd.DataFrame, periodo: int = 14) -> dict:
    """
    Directional Movement (DM) + ADX.
    +DI / -DI miden dirección, ADX mide FUERZA de la tendencia.
      ADX > 25 → tendencia fuerte
      +DI > -DI → tendencia alcista
    """
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    tr = atr(df, periodo) * periodo  # aproximación de TR suavizado
    atr_s = atr(df, periodo)

    plus_dm_s = pd.Series(plus_dm, index=df.index).ewm(alpha=1/periodo, adjust=False).mean()
    minus_dm_s = pd.Series(minus_dm, index=df.index).ewm(alpha=1/periodo, adjust=False).mean()

    plus_di = 100 * plus_dm_s / atr_s.replace(0, np.nan)
    minus_di = 100 * minus_dm_s / atr_s.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1/periodo, adjust=False).mean()

    return {"adx": adx, "plus_di": plus_di, "minus_di": minus_di}


def vwap_aprox(df: pd.DataFrame, periodo: int = 20) -> pd.Series:
    """
    VWAP aproximado con datos diarios (rolling).
    Usa typical price = (H+L+C)/3 ponderado por volumen.
    NO es el VWAP intradiario real, pero da una referencia de
    precio promedio ponderado por volumen del período.
    """
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].replace(0, np.nan).ffill().fillna(1)
    pv = (tp * vol).rolling(window=periodo).sum()
    v = vol.rolling(window=periodo).sum()
    return pv / v.replace(0, np.nan)


def bollinger(serie: pd.Series, periodo=20, num_std=2) -> dict:
    media = sma(serie, periodo)
    std = serie.rolling(window=periodo).std()
    return {"media": media, "sup": media + num_std*std, "inf": media - num_std*std}


def fibonacci(df: pd.DataFrame, ventana: int = 60) -> dict:
    """
    Niveles de retroceso de Fibonacci sobre el swing de las últimas
    `ventana` ruedas. Devuelve los niveles y dónde está el precio actual.
    """
    sub = df.tail(ventana)
    if len(sub) < 5:
        return {}
    maximo = float(sub["high"].max())
    minimo = float(sub["low"].min())
    rango = maximo - minimo
    if rango == 0:
        return {}

    niveles = {
        "0.0%":   maximo,
        "23.6%":  maximo - 0.236 * rango,
        "38.2%":  maximo - 0.382 * rango,
        "50.0%":  maximo - 0.500 * rango,
        "61.8%":  maximo - 0.618 * rango,
        "78.6%":  maximo - 0.786 * rango,
        "100.0%": minimo,
    }
    precio = float(df["close"].iloc[-1])

    # ¿Entre qué dos niveles está el precio?
    zona = "—"
    items = list(niveles.items())
    for i in range(len(items) - 1):
        n_alto, v_alto = items[i]
        n_bajo, v_bajo = items[i+1]
        if v_bajo <= precio <= v_alto:
            zona = f"{n_bajo}–{n_alto}"
            break

    return {"niveles": niveles, "precio": precio, "zona": zona,
            "maximo": maximo, "minimo": minimo}


# ─────────────────────────────────────────────────────────────
#  ANÁLISIS COMPLETO + SCORE COMBINADO
# ─────────────────────────────────────────────────────────────

def analizar_completo(df: pd.DataFrame) -> dict | None:
    """
    Calcula todos los indicadores y arma un score 0-100.

    El score combina señales direccionales:
      RSI, MACD, EMA(tendencia), SMA200, Estocástico, ADX/DI, VWAP, Bollinger.
    ATR y Fibonacci se reportan como contexto (no votan en el score,
    porque son de volatilidad / niveles, no direccionales).

    Score:  0-35 bajista | 35-50 neutral-bajista | 50-65 neutral-alcista | 65-100 alcista
    """
    if df is None or len(df) < 50:
        return None

    close = df["close"]
    precio = float(close.iloc[-1])

    # ── Calcular indicadores ──
    ema20 = ema(close, 20); ema50 = ema(close, 50)
    sma200 = sma(close, 200)
    rsi14 = rsi(close, 14)
    macd_d = macd(close)
    stoch = estocastico(df)
    atr14 = atr(df, 14)
    dm = adx_dm(df, 14)
    vwap = vwap_aprox(df, 20)
    boll = bollinger(close, 20, 2)
    fib = fibonacci(df, 60)

    # Valores actuales (última rueda)
    def _last(s):
        try:
            v = float(s.iloc[-1])
            return v if not np.isnan(v) else None
        except Exception:
            return None

    v_ema20, v_ema50 = _last(ema20), _last(ema50)
    v_sma200 = _last(sma200)
    v_rsi = _last(rsi14)
    v_macd, v_signal, v_hist = _last(macd_d["macd"]), _last(macd_d["signal"]), _last(macd_d["hist"])
    v_hist_prev = _last(macd_d["hist"].iloc[:-1]) if len(macd_d["hist"]) > 1 else None
    v_k, v_d = _last(stoch["k"]), _last(stoch["d"])
    v_atr = _last(atr14)
    v_adx, v_pdi, v_mdi = _last(dm["adx"]), _last(dm["plus_di"]), _last(dm["minus_di"])
    v_vwap = _last(vwap)
    v_boll_sup, v_boll_inf = _last(boll["sup"]), _last(boll["inf"])

    # ── Sistema de votación para el score ──
    votos = []   # cada uno: (nombre, señal, peso, detalle)

    # RSI (peso 1)
    if v_rsi is not None:
        if v_rsi >= 70:    s, txt = -1, f"sobrecompra ({v_rsi:.0f})"
        elif v_rsi <= 30:  s, txt = +1, f"sobreventa ({v_rsi:.0f})"
        elif v_rsi >= 55:  s, txt = +0.5, f"impulso alcista ({v_rsi:.0f})"
        elif v_rsi <= 45:  s, txt = -0.5, f"impulso bajista ({v_rsi:.0f})"
        else:              s, txt = 0, f"neutral ({v_rsi:.0f})"
        votos.append(("RSI", s, 1.0, txt))

    # MACD (peso 1.5) — histograma + cruce
    if v_macd is not None and v_signal is not None:
        if v_macd > v_signal and (v_hist_prev is None or v_hist > v_hist_prev):
            s, txt = +1, "MACD>señal, hist creciente"
        elif v_macd > v_signal:
            s, txt = +0.5, "MACD>señal"
        elif v_macd < v_signal and (v_hist_prev is None or v_hist < v_hist_prev):
            s, txt = -1, "MACD<señal, hist cayendo"
        else:
            s, txt = -0.5, "MACD<señal"
        votos.append(("MACD", s, 1.5, txt))

    # Tendencia EMA (peso 1.5)
    if v_ema20 and v_ema50:
        if precio > v_ema20 > v_ema50:   s, txt = +1, "precio>EMA20>EMA50 (alcista)"
        elif precio < v_ema20 < v_ema50: s, txt = -1, "precio<EMA20<EMA50 (bajista)"
        elif v_ema20 > v_ema50:          s, txt = +0.5, "EMA20>EMA50"
        else:                            s, txt = -0.5, "EMA20<EMA50"
        votos.append(("Tendencia EMA", s, 1.5, txt))

    # SMA200 (peso 1) — tendencia de largo plazo
    if v_sma200:
        if precio > v_sma200: s, txt = +1, "sobre SMA200 (alcista LP)"
        else:                 s, txt = -1, "bajo SMA200 (bajista LP)"
        votos.append(("SMA200", s, 1.0, txt))

    # Estocástico (peso 1)
    if v_k is not None and v_d is not None:
        if v_k >= 80:   s, txt = -1, f"sobrecompra ({v_k:.0f})"
        elif v_k <= 20: s, txt = +1, f"sobreventa ({v_k:.0f})"
        elif v_k > v_d: s, txt = +0.5, "%K>%D"
        else:           s, txt = -0.5, "%K<%D"
        votos.append(("Estocástico", s, 1.0, txt))

    # ADX/DM (peso 1.5) — fuerza + dirección
    if v_adx is not None and v_pdi is not None and v_mdi is not None:
        fuerte = v_adx >= 25
        if v_pdi > v_mdi:
            s = +1 if fuerte else +0.5
            txt = f"+DI>-DI, ADX {v_adx:.0f}" + (" (fuerte)" if fuerte else " (débil)")
        else:
            s = -1 if fuerte else -0.5
            txt = f"-DI>+DI, ADX {v_adx:.0f}" + (" (fuerte)" if fuerte else " (débil)")
        votos.append(("ADX/DM", s, 1.5, txt))

    # VWAP aprox (peso 0.5)
    if v_vwap:
        if precio > v_vwap: s, txt = +0.5, "precio sobre VWAP"
        else:               s, txt = -0.5, "precio bajo VWAP"
        votos.append(("VWAP aprox", s, 0.5, txt))

    # Bollinger (peso 0.5)
    if v_boll_sup and v_boll_inf:
        if precio >= v_boll_sup:   s, txt = -0.5, "tocando banda superior"
        elif precio <= v_boll_inf: s, txt = +0.5, "tocando banda inferior"
        else:                      s, txt = 0, "dentro de bandas"
        votos.append(("Bollinger", s, 0.5, txt))

    # ── Calcular score 0-100 ──
    peso_total = sum(v[2] for v in votos)
    if peso_total == 0:
        return None
    suma_ponderada = sum(v[1] * v[2] for v in votos)
    # Normalizar de [-1,+1] a [0,100]
    score = 50 + (suma_ponderada / peso_total) * 50
    score = max(0, min(100, score))

    # Señal global
    if score >= 65:   senal, color = "ALCISTA", "#00d4aa"
    elif score >= 50: senal, color = "NEUTRAL-ALCISTA", "#7ac4e8"
    elif score >= 35: senal, color = "NEUTRAL-BAJISTA", "#ffc107"
    else:             senal, color = "BAJISTA", "#ff6b6b"

    # ATR como % del precio (volatilidad relativa)
    atr_pct = (v_atr / precio * 100) if v_atr and precio else None

    return {
        "precio": round(precio, 2),
        "score": round(score, 1),
        "senal": senal,
        "color": color,
        "votos": [(n, round(s, 2), p, t) for n, s, p, t in votos],
        # valores crudos
        "rsi": round(v_rsi, 1) if v_rsi else None,
        "ema20": round(v_ema20, 2) if v_ema20 else None,
        "ema50": round(v_ema50, 2) if v_ema50 else None,
        "sma200": round(v_sma200, 2) if v_sma200 else None,
        "macd": round(v_macd, 3) if v_macd else None,
        "macd_signal": round(v_signal, 3) if v_signal else None,
        "macd_hist": round(v_hist, 3) if v_hist else None,
        "stoch_k": round(v_k, 1) if v_k else None,
        "stoch_d": round(v_d, 1) if v_d else None,
        "atr": round(v_atr, 2) if v_atr else None,
        "atr_pct": round(atr_pct, 2) if atr_pct else None,
        "adx": round(v_adx, 1) if v_adx else None,
        "plus_di": round(v_pdi, 1) if v_pdi else None,
        "minus_di": round(v_mdi, 1) if v_mdi else None,
        "vwap": round(v_vwap, 2) if v_vwap else None,
        "fibonacci": fib,
        "n_datos": len(df),
        "sparkline": [round(float(x), 2) for x in close.tail(40).tolist()],
    }


# ─────────────────────────────────────────────────────────────
#  MÉTRICAS DE RIESGO DE CARTERA
# ─────────────────────────────────────────────────────────────

def _retornos_diarios(serie_precios: pd.Series) -> pd.Series:
    return serie_precios.pct_change().dropna()


def volatilidad_anualizada(serie_precios: pd.Series, periodos_año: int = 252) -> float | None:
    r = _retornos_diarios(serie_precios)
    if len(r) < 2:
        return None
    return float(r.std() * np.sqrt(periodos_año))


def sharpe(serie_precios: pd.Series, tasa_libre: float = 0.0,
           periodos_año: int = 252) -> float | None:
    r = _retornos_diarios(serie_precios)
    if len(r) < 2 or r.std() == 0:
        return None
    exceso = r.mean() - tasa_libre / periodos_año
    return float(exceso / r.std() * np.sqrt(periodos_año))


def drawdown_maximo(serie_precios: pd.Series) -> float | None:
    if len(serie_precios) < 2:
        return None
    maximo_acum = serie_precios.cummax()
    drawdown = (serie_precios - maximo_acum) / maximo_acum
    return float(drawdown.min())


def valor_en_riesgo(serie_precios: pd.Series, confianza: float = 0.95) -> float | None:
    r = _retornos_diarios(serie_precios)
    if len(r) < 5:
        return None
    return float(np.percentile(r, (1 - confianza) * 100))


def resumen_riesgo(historial: list) -> dict | None:
    """
    Recibe la lista del historial_patrimonio.json (dicts con 'fecha' y 'patrimonio').
    Devuelve un dict con todas las métricas de riesgo.
    """
    if not historial or len(historial) < 5:
        return None
    precios = pd.Series([h["patrimonio"] for h in historial], dtype=float)
    vol = volatilidad_anualizada(precios)
    sp = sharpe(precios)
    dd = drawdown_maximo(precios)
    var95 = valor_en_riesgo(precios)
    ultimo = float(precios.iloc[-1])
    var95_ars = var95 * ultimo if var95 is not None else None
    return {
        "volatilidad_anual": round(vol * 100, 1) if vol is not None else None,
        "sharpe": round(sp, 2) if sp is not None else None,
        "drawdown_maximo_pct": round(dd * 100, 1) if dd is not None else None,
        "var_95_pct": round(var95 * 100, 2) if var95 is not None else None,
        "var_95_ars": round(var95_ars, 0) if var95_ars is not None else None,
        "n_dias": len(historial),
    }


if __name__ == "__main__":
    # Prueba con datos sintéticos
    np.random.seed(42)
    n = 250
    precios = 100 + np.cumsum(np.random.randn(n) * 2 + 0.1)
    df = pd.DataFrame({
        "date": pd.date_range("2025-09-01", periods=n),
        "open": precios + np.random.randn(n),
        "high": precios + abs(np.random.randn(n)) * 2,
        "low": precios - abs(np.random.randn(n)) * 2,
        "close": precios,
        "volume": abs(np.random.randn(n)) * 10000 + 50000,
    })
    res = analizar_completo(df)
    print(f"Score: {res['score']} → {res['senal']}")
    print(f"Precio: ${res['precio']}")
    print(f"RSI: {res['rsi']} | ADX: {res['adx']} | ATR%: {res['atr_pct']}")
    print(f"\nVotos:")
    for nombre, s, peso, txt in res["votos"]:
        signo = "+" if s > 0 else ("=" if s == 0 else "-")
        print(f"  [{signo}] {nombre}: {txt}")
    print(f"\nFibonacci zona: {res['fibonacci'].get('zona', '—')}")
