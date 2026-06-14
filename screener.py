"""
=============================================================
  SCREENER TÉCNICO — Cartera Inversor v6
  Ezequiel | junio 2026

  Corre indicadores_avanzados sobre un universo de:
    - Acciones líderes del MERVAL (por sector)
    - CEDEARs accesibles y recomendados (por sector)
    - Tu cartera + watchlist actual

  Para cada papel: trae histórico de Rava, calcula el score 0-100
  combinado y devuelve un ranking.

  ⚠️ USO RESPONSABLE: este screener hace 1 request a Rava por papel.
  Con ~40 papeles son ~40 requests. Corré el screener como MÁXIMO
  1 vez al día (idealmente post-cierre). NO lo metas en loop.
  Por eso en el reporte es OPT-IN (flag --screener).

  Selección de papeles basada en informes de brokers (jun 2026):
    - Energía lidera por convicción: YPF, Pampa, TGS, Vista
    - Bancos: alto riesgo/alto retorno: GGAL, BMA, BBAR
    - Tech CEDEARs: NVDA, AAPL, GOOGL, MELI
    - Defensivos: KO, WMT, BRKB
    - Diversificación: SPY, QQQ

  Dependencias: pandas, fuente_rava, indicadores_avanzados
=============================================================
"""

import time

try:
    import fuente_rava
    RAVA_OK = True
except ImportError:
    RAVA_OK = False

import indicadores_avanzados as ta


# ═══════════════════════════════════════════════════════════════════
#  UNIVERSO DE ACTIVOS — editá para agregar/quitar papeles
#  (ticker_rava, nombre, sector, tipo)
# ═══════════════════════════════════════════════════════════════════

UNIVERSO_MERVAL = [
    # ── Energía / Petróleo & Gas (sector preferido por analistas) ──
    ("YPFD", "YPF",                "Energía",   "accion_arg"),
    ("PAMP", "Pampa Energía",      "Energía",   "accion_arg"),
    ("TGSU2","Transp. Gas del Sur","Energía",   "accion_arg"),
    ("TGNO4","Transp. Gas Norte",  "Energía",   "accion_arg"),
    ("CEPU", "Central Puerto",     "Energía",   "accion_arg"),
    # ── Utilities / Servicios públicos (alta beta) ──
    ("TRAN", "Transener",          "Utilities", "accion_arg"),
    ("EDN",  "Edenor",             "Utilities", "accion_arg"),
    ("METR", "Metrogas",           "Utilities", "accion_arg"),
    # ── Bancos (alto riesgo / alto retorno) ──
    ("GGAL", "Grupo Galicia",      "Bancos",    "accion_arg"),
    ("BMA",  "Banco Macro",        "Bancos",    "accion_arg"),
    ("BBAR", "BBVA Argentina",     "Bancos",    "accion_arg"),
    ("SUPV", "Supervielle",        "Bancos",    "accion_arg"),
    # ── Industria / Materiales ──
    ("TXAR", "Ternium Argentina",  "Materiales","accion_arg"),
    ("ALUA", "Aluar",              "Materiales","accion_arg"),
    ("LOMA", "Loma Negra",         "Materiales","accion_arg"),
    # ── Real Estate ──
    ("IRSA", "IRSA",               "Real Estate","accion_arg"),
    ("CRES", "Cresud",             "Real Estate","accion_arg"),
    # ── Telecom / Tech local ──
    ("TECO2","Telecom Argentina",  "Telecom",   "accion_arg"),
    ("CVH",  "Cablevisión Holding","Telecom",   "accion_arg"),
    ("MIRG", "Mirgor",             "Tech/Cons", "accion_arg"),
    # ── Agro / Alimentos ──
    ("AGRO", "Adecoagro",          "Agro",      "accion_arg"),
    ("MOLA", "Molinos Agro",       "Agro",      "accion_arg"),
    # ── Consumo / Otros ──
    ("COME", "Soc. Comercial Plata","Holding",  "accion_arg"),
    ("VALO", "Grupo Fin. Valores", "Bancos",    "accion_arg"),
    ("BYMA", "Bolsas y Mercados",  "Bancos",    "accion_arg"),
]

UNIVERSO_CEDEARS = [
    # ── Tech USA (no más de 30-40% de cartera CEDEAR según analistas) ──
    ("NVDA", "NVIDIA",             "Tech",      "cedear"),
    ("AAPL", "Apple",              "Tech",      "cedear"),
    ("GOOGL","Alphabet/Google",    "Tech",      "cedear"),
    ("MSFT", "Microsoft",          "Tech",      "cedear"),
    ("AMZN", "Amazon",             "Tech/Cons", "cedear"),
    # ── Latam / Emergentes ──
    ("MELI", "MercadoLibre",       "E-commerce","cedear"),
    ("VIST", "Vista Energy",       "Energía",   "cedear"),
    ("NU",   "Nubank",             "Fintech",   "cedear"),
    ("GLOB", "Globant",            "Tech",      "cedear"),
    # ── Defensivos / Dividendos ──
    ("KO",   "Coca-Cola",          "Consumo",   "cedear"),
    ("WMT",  "Walmart",            "Consumo",   "cedear"),
    ("XOM",  "ExxonMobil",         "Energía",   "cedear"),
    ("BRKB", "Berkshire Hathaway", "Holding",   "cedear"),
    ("JNJ",  "Johnson & Johnson",  "Salud",     "cedear"),
    ("MDT",  "Medtronic",          "Salud",     "cedear"),
    # ── ETFs (diversificación) ──
    ("SPY",  "S&P 500 ETF",        "ETF Index", "cedear"),
    ("QQQ",  "Nasdaq 100 ETF",     "ETF Index", "cedear"),
    ("XLP",  "Consumer Staples ETF","ETF Sector","cedear"),
]


def analizar_papel(ticker: str, nombre: str, sector: str, tipo: str,
                   pausa: float = 0.3) -> dict | None:
    """Trae histórico de Rava y corre el análisis completo."""
    if not RAVA_OK:
        return None
    try:
        df = fuente_rava.get_perfil_historico(ticker)
        if df is None or len(df) < 50:
            return None
        res = ta.analizar_completo(df)
        if res is None:
            return None
        res.update({"ticker": ticker, "nombre": nombre,
                    "sector": sector, "tipo": tipo})
        time.sleep(pausa)  # respetar a Rava
        return res
    except Exception:
        return None


def correr_screener(incluir_merval=True, incluir_cedears=True,
                    log_fn=None) -> list:
    """
    Corre el screener sobre el universo seleccionado.
    Devuelve lista de resultados ordenada por score descendente.
    """
    def _log(msg):
        if log_fn:
            log_fn(msg)
        else:
            print(msg)

    universo = []
    if incluir_merval:
        universo += UNIVERSO_MERVAL
    if incluir_cedears:
        universo += UNIVERSO_CEDEARS

    resultados = []
    for i, (ticker, nombre, sector, tipo) in enumerate(universo, 1):
        _log(f"  [{i}/{len(universo)}] {ticker} ({nombre})...")
        res = analizar_papel(ticker, nombre, sector, tipo)
        if res:
            resultados.append(res)

    resultados.sort(key=lambda r: -r["score"])
    return resultados


if __name__ == "__main__":
    print("=== Screener técnico (prueba) ===\n")
    if not RAVA_OK:
        print("fuente_rava no disponible — correr desde la carpeta del proyecto")
        raise SystemExit(0)

    resultados = correr_screener(incluir_merval=True, incluir_cedears=True)
    print(f"\n{'='*60}")
    print(f"RANKING POR SCORE TÉCNICO ({len(resultados)} papeles)")
    print(f"{'='*60}")
    print(f"{'Ticker':<8}{'Score':<8}{'Señal':<18}{'Sector':<14}RSI")
    for r in resultados:
        print(f"{r['ticker']:<8}{r['score']:<8}{r['senal']:<18}{r['sector']:<14}{r.get('rsi','—')}")
