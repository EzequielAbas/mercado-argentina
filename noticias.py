"""
=============================================================
  NOTICIAS FINANCIERAS — módulo para Cartera Inversor v6
  Ezequiel | junio 2026

  Trae titulares de noticias financieras de múltiples fuentes:
    - Ámbito Financiero  (RSS economía / finanzas)
    - El Cronista        (RSS finanzas / mercados)
    - Infobae Economía   (respaldo, RSS)
    - Investing.com      (noticias internacionales, español)
    - Yahoo Finance      (noticias por ticker de tu cartera)
    - Google News        (mercado argentino + bonos)

  Usa FEEDS RSS en vez de scraping → estable, permitido.

  Dependencias:
    (ninguna nueva obligatoria — usa requests + xml stdlib)
    pip install feedparser   (opcional, recomendado)
=============================================================
"""

import re
import html
import datetime
from xml.etree import ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
    requests.packages.urllib3.disable_warnings()
except ImportError:
    raise SystemExit("[!] Instalar: pip install requests")

try:
    import feedparser
    _FEEDPARSER = True
except ImportError:
    _FEEDPARSER = False


# ── Feeds RSS locales (Argentina) ──
FEEDS = [
    {"medio": "Ámbito", "url": "https://www.ambito.com/rss/pages/economia.xml"},
    {"medio": "Ámbito Finanzas", "url": "https://www.ambito.com/rss/pages/finanzas.xml"},
    {"medio": "El Cronista", "url": "https://www.cronista.com/files/rss/finanzas-mercados.xml"},
    {"medio": "Infobae Economía", "url": "https://www.infobae.com/economia/rss/"},
]

# ── Feeds internacionales ──
FEEDS_INTL = [
    {"medio": "Investing.com", "url": "https://es.investing.com/rss/news.rss"},
]

# ── Google News searches (mercado argentino) ──
GOOGLE_NEWS_QUERIES = [
    "merval acciones bonos argentina",
    "dolar MEP CCL argentina",
]

# Palabras clave para destacar noticias relevantes a TU cartera
KEYWORDS_RELEVANTES = [
    "bono", "bonar", "ao27", "al30", "gd30", "riesgo país", "dólar", "mep",
    "blue", "cer", "inflación", "fci", "cedear", "tasa", "bcra",
    "merval", "byma", "deuda", "fmi", "reservas", "plazo fijo",
    "galicia", "ggal", "bbva", "bbar", "macro", "bma", "ternium", "txar",
    "mercadolibre", "meli", "ypf", "ymcwo",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (CarteraInversor/4.0; lectura RSS personal)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def _limpiar(texto: str) -> str:
    """Quita tags HTML y normaliza entidades."""
    if not texto:
        return ""
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = html.unescape(texto)
    return texto.strip()


def _parse_con_feedparser(url: str, medio: str, max_items: int) -> list:
    out = []
    try:
        d = feedparser.parse(url, request_headers=HEADERS)
        for e in d.entries[:max_items]:
            out.append({
                "medio":   medio,
                "titulo":  _limpiar(e.get("title", "")),
                "resumen": _limpiar(e.get("summary", ""))[:200],
                "link":    e.get("link", ""),
                "fecha":   e.get("published", "")[:25],
            })
    except Exception:
        pass
    return out


def _parse_manual(url: str, medio: str, max_items: int) -> list:
    """Parser RSS mínimo sin dependencias externas."""
    out = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        # RSS clásico: channel/item
        items = root.findall(".//item")
        for it in items[:max_items]:
            titulo = it.findtext("title", "")
            desc = it.findtext("description", "")
            link = it.findtext("link", "")
            pub = it.findtext("pubDate", "")
            out.append({
                "medio":   medio,
                "titulo":  _limpiar(titulo),
                "resumen": _limpiar(desc)[:200],
                "link":    (link or "").strip(),
                "fecha":   (pub or "")[:25],
            })
    except Exception:
        pass
    return out


def _es_relevante(noticia: dict) -> bool:
    texto = (noticia["titulo"] + " " + noticia.get("resumen", "")).lower()
    return any(kw in texto for kw in KEYWORDS_RELEVANTES)


def _detect_tickers(texto: str, tickers_cartera: list) -> list:
    """Detecta qué tickers de la cartera se mencionan en un texto."""
    texto_upper = texto.upper()
    found = []
    _NOMBRE_MAP = {
        "GGAL": ["GALICIA", "GGAL"],
        "BBAR": ["BBVA", "BBAR", "FRANCES"],
        "BMA": ["BANCO MACRO", "BMA"],
        "TXAR": ["TERNIUM", "TXAR"],
        "MELI": ["MERCADOLIBRE", "MERCADO LIBRE", "MELI"],
        "YMCWO": ["YPF", "YMCWO"],
        "AL30": ["AL30"],
        "GD30": ["GD30"],
        "AO27": ["AO27"],
        "TZX28": ["TZX28", "BONO CER"],
        "S30S6": ["LECAP", "S30S6"],
    }
    for tk in tickers_cartera:
        names = _NOMBRE_MAP.get(tk.upper(), [tk.upper()])
        for name in names:
            if name in texto_upper:
                found.append(tk.upper())
                break
    return list(set(found))


def _fetch_yahoo_ticker(ticker: str, max_items: int = 5) -> list:
    """Trae noticias de Yahoo Finance para un ticker específico."""
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    items = _parse_manual(url, "Yahoo Finance", max_items)
    for item in items:
        item["_source_ticker"] = ticker.upper()
        item["_tipo"] = "ticker"
    return items


def _fetch_google_news(query: str, max_items: int = 8) -> list:
    """Trae noticias de Google News para una búsqueda."""
    url = f"https://news.google.com/rss/search?q={query}&hl=es-419&gl=AR&ceid=AR:es-419"
    return _parse_manual(url, "Google News", max_items)


def obtener_noticias(max_por_feed: int = 6, solo_relevantes: bool = False,
                     log_fn=None, tickers_cartera: list = None) -> list:
    """
    Devuelve lista de noticias de todos los feeds.
      max_por_feed    → cuántos titulares traer de cada medio
      solo_relevantes → si True, filtra por keywords de tu cartera
      tickers_cartera → lista de tickers para buscar en Yahoo Finance
      log_fn          → función de log opcional
    """
    def _log(msg, level="INFO"):
        if log_fn:
            log_fn(msg, level)

    todas = []
    titulos_vistos = set()

    def _add_items(items):
        for item in items:
            key = item["titulo"][:60].lower()
            if key not in titulos_vistos:
                titulos_vistos.add(key)
                todas.append(item)

    # Feeds en paralelo para no demorar
    all_feeds = FEEDS + FEEDS_INTL
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {}

        # Feeds RSS locales + internacionales
        for feed in all_feeds:
            if _FEEDPARSER:
                futures[pool.submit(_parse_con_feedparser, feed["url"], feed["medio"], max_por_feed)] = feed["medio"]
            else:
                futures[pool.submit(_parse_manual, feed["url"], feed["medio"], max_por_feed)] = feed["medio"]

        # Yahoo Finance por ticker
        if tickers_cartera:
            yahoo_tickers = [t for t in tickers_cartera if not t.startswith("_")]
            for tk in yahoo_tickers[:8]:
                futures[pool.submit(_fetch_yahoo_ticker, tk, 4)] = f"Yahoo:{tk}"

        # Google News queries
        for q in GOOGLE_NEWS_QUERIES:
            futures[pool.submit(_fetch_google_news, q, 6)] = f"Google:{q[:20]}"

        for future in as_completed(futures):
            nombre = futures[future]
            try:
                items = future.result()
                if items:
                    _log(f"  {len(items)} titulares de {nombre}", "OK")
                    _add_items(items)
            except Exception:
                _log(f"  sin respuesta de {nombre}", "WARN")

    # Detectar tickers mencionados
    if tickers_cartera:
        for n in todas:
            texto = n["titulo"] + " " + n.get("resumen", "")
            source_tk = n.get("_source_ticker")
            detected = _detect_tickers(texto, tickers_cartera)
            if source_tk and source_tk not in detected:
                detected.append(source_tk)
            n["_tickers_mencionados"] = detected

    # Marca relevancia
    for n in todas:
        n["relevante"] = _es_relevante(n) or bool(n.get("_tickers_mencionados"))

    if solo_relevantes:
        todas = [n for n in todas if n["relevante"]]

    # Ordenar: con tickers primero, luego relevantes, luego el resto
    def _sort_key(n):
        has_tickers = bool(n.get("_tickers_mencionados"))
        return (not has_tickers, not n.get("relevante", False))
    todas.sort(key=_sort_key)

    return todas


# ═══════════════════════════════════════════════════════════
#  PRUEBA STANDALONE
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Prueba de noticias.py")
    print(f"feedparser disponible: {_FEEDPARSER}")
    print("=" * 50)
    test_tickers = ["AL30", "GD30", "GGAL", "BBAR", "MELI", "BMA", "TXAR"]
    noticias = obtener_noticias(
        max_por_feed=4, tickers_cartera=test_tickers,
        log_fn=lambda m, l="INFO": print(f"  [{l}] {m}"))
    print(f"\nTotal: {len(noticias)} noticias\n")
    for n in noticias[:20]:
        tks = n.get("_tickers_mencionados", [])
        marca = f"[{','.join(tks)}]" if tks else ("★" if n["relevante"] else " ")
        print(f"{marca:14s} [{n['medio']:16s}] {n['titulo'][:65]}")
