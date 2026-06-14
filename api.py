"""
api.py — API REST pública del MERCADO ARGENTINO (sin datos personales).

Expone como JSON lo mismo que consumen los paneles de mercado del reporte:
macro, FX implícito, bonos (soberanos USD / CER / LECAP / ONs), noticias,
análisis técnico y screener. NUNCA toca cartera, sueldos ni liquidez:
eso vive en el repo privado, que CONSUME esta API (o importa estos módulos).

Uso local:
    pip install -r requirements.txt
    uvicorn api:app --reload --port 8000
    # http://127.0.0.1:8000/docs  ← Swagger interactivo

Deploy (Render / Railway / VPS): mismo comando, puerto $PORT.
"""

from __future__ import annotations

import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import fuente_argentinadatos as adatos
import fuente_bonistas as bonistas
import fuente_rava as rava
import noticias as news_mod

try:
    import screener as screener_mod
    SCREENER_OK = True
except ImportError:
    SCREENER_OK = False

try:
    import analisis_tecnico as at_mod
    AT_OK = True
except ImportError:
    AT_OK = False

app = FastAPI(
    title="Mercado Argentino API",
    description="Datos públicos de mercado (Bonistas, Rava, ArgentinaDatos, RSS). Sin datos personales.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"]
)

# ── Cache simple en memoria (TTL segundos) para no castigar a las fuentes ──
_CACHE: dict[str, tuple[float, object]] = {}

def _cached(key: str, ttl: int, fn):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


def _df_records(df):
    """DataFrame → lista de dicts JSON-safe (NaN → None)."""
    import math
    if df is None or getattr(df, "empty", True):
        return []
    recs = df.to_dict(orient="records")
    for r in recs:
        for k, v in r.items():
            if isinstance(v, float) and math.isnan(v):
                r[k] = None
            elif hasattr(v, "isoformat"):
                r[k] = v.isoformat()
    return recs


# ═══════════════════════════ ENDPOINTS ═══════════════════════════

@app.get("/salud")
def salud():
    return {"ok": True, "screener": SCREENER_OK, "analisis_tecnico": AT_OK}


@app.get("/macro")
def macro():
    """MEP, CCL, oficial, blue, riesgo país y Merval (ArgentinaDatos + Rava)."""
    def _build():
        out = adatos.get_macro() or {}
        home = rava.get_home() or {}
        if home.get("merval"):
            out["merval"] = home["merval"].get("valor")
        if not out.get("riesgo_pais") and home.get("riesgo_pais"):
            out["riesgo_pais"] = home["riesgo_pais"].get("valor")
        return out
    return _cached("macro", 300, _build)


@app.get("/dolares")
def dolares():
    """Todas las cotizaciones de dólar (compra/venta/fecha) de ArgentinaDatos."""
    return _cached("dolares", 300, adatos.get_dolares)


@app.get("/riesgo-pais")
def riesgo_pais():
    rp = _cached("rp", 300, adatos.get_riesgo_pais)
    if not rp:
        raise HTTPException(503, "Fuente no disponible")
    return rp


@app.get("/fx")
def fx():
    """FX implícito por instrumento (MEP/Cable por bono) — Bonistas."""
    def _build():
        return {
            "estado_mercado": bonistas.get_market_status(),
            "resumen": bonistas.get_fx_summary(),
            "instrumentos": _df_records(bonistas.get_fx()),
        }
    return _cached("fx", 300, _build)


@app.get("/bonos")
def bonos(
    familia: Optional[str] = Query(
        None,
        description="soberanos_usd | cer | lecap | on (vacío = todos)",
    )
):
    """Tabla de bonos de Bonistas (precio, TIR, duration, paridad, vto)."""
    def _build():
        df = bonistas.get_bonds()
        return df
    df = _cached("bonos_df", 300, _build)
    if familia:
        fams = bonistas.get_bonds_by_family(df)
        # match flexible de clave
        for k, v in fams.items():
            if familia.lower() in str(k).lower():
                return {"familia": k, "bonos": _df_records(v)}
        raise HTTPException(404, f"Familia '{familia}' no encontrada. Disponibles: {list(fams)}")
    return {"bonos": _df_records(df)}


@app.get("/fci/{tipo}")
def fci(tipo: str = "mercadoDinero"):
    """FCIs con última cuotaparte (ArgentinaDatos): mercadoDinero | rentaFija | rentaVariable | rentaMixta."""
    return _cached(f"fci_{tipo}", 3600, lambda: adatos.get_fci(tipo))


@app.get("/noticias")
def noticias(relevantes: bool = True, max_por_feed: int = 6):
    """Noticias financieras de feeds RSS, opcionalmente filtradas por keywords de inversión."""
    return _cached(
        f"news_{relevantes}_{max_por_feed}", 600,
        lambda: news_mod.obtener_noticias(max_por_feed=max_por_feed, solo_relevantes=relevantes),
    )


@app.get("/tecnico/{ticker}")
def tecnico(ticker: str, dias: int = 120):
    """Análisis técnico (RSI/EMA/señal) sobre histórico de yfinance. Sin IOL (credencial privada)."""
    if not AT_OK:
        raise HTTPException(503, "Módulo de análisis técnico no disponible")
    df = at_mod.historico_yfinance(ticker, dias=dias)
    if df is None or df.empty:
        raise HTTPException(404, f"Sin histórico para {ticker}")
    res = at_mod.analizar(df)
    if not res:
        raise HTTPException(500, "No se pudo analizar")
    return {"ticker": ticker.upper(), **res}


@app.get("/screener")
def screener(merval: bool = True, cedears: bool = True):
    """Screener técnico completo (LENTO: ~1 request por papel). Cache 30 min."""
    if not SCREENER_OK:
        raise HTTPException(503, "Screener no disponible")
    def _run():
        res = screener_mod.correr_screener(incluir_merval=merval, incluir_cedears=cedears)
        return _df_records(res) if hasattr(res, "to_dict") else res
    return _cached(f"screener_{merval}_{cedears}", 1800, _run)


@app.get("/feriados/{anio}")
def feriados(anio: int):
    return _cached(f"feriados_{anio}", 86400, lambda: adatos.get_feriados(anio))
