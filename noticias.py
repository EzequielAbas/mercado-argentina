"""
=============================================================
  NOTICIAS FINANCIERAS — módulo para Cartera Inversor v4
  Ezequiel | junio 2026

  Trae titulares de noticias financieras argentinas y los
  integra al reporte. Usa FEEDS RSS en vez de scraping de HTML.

  ¿Por qué RSS y no scraping?
    - Los feeds RSS los publica el propio medio PARA ser leídos
      por programas → es el método correcto y permitido.
    - No se rompe cuando el sitio cambia el diseño.
    - No te bloquean la IP.

  FUENTES:
    - Ámbito Financiero  (RSS economía / finanzas)
    - El Cronista        (RSS finanzas / mercados)
    - Infobae Economía   (respaldo, RSS)

  Solo necesita la librería estándar + requests (que ya usás).
  Opcional: feedparser (más robusto). Si no está, usa un parser
  propio mínimo basado en xml.etree.

  Dependencias:
    (ninguna nueva obligatoria — usa requests + xml stdlib)
    pip install feedparser   (opcional, recomendado)
=============================================================
"""

import re
import html
import datetime
from xml.etree import ElementTree as ET

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


# ── Feeds RSS (verificá/actualizá las URLs si alguna cambia) ──
FEEDS = [
    {
        "medio": "Ámbito",
        "url": "https://www.ambito.com/rss/pages/economia.xml",
    },
    {
        "medio": "Ámbito Finanzas",
        "url": "https://www.ambito.com/rss/pages/finanzas.xml",
    },
    {
        "medio": "El Cronista",
        "url": "https://www.cronista.com/files/rss/finanzas-mercados.xml",
    },
    {
        "medio": "Infobae Economía",
        "url": "https://www.infobae.com/economia/rss/",
    },
]

# Palabras clave para destacar noticias relevantes a TU cartera
KEYWORDS_RELEVANTES = [
    "bono", "bonar", "ao27", "al30", "riesgo país", "dólar", "mep",
    "blue", "cer", "inflación", "fci", "cedear", "tasa", "bcra",
    "merval", "byma", "deuda", "fmi", "reservas", "plazo fijo",
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
    texto = (noticia["titulo"] + " " + noticia["resumen"]).lower()
    return any(kw in texto for kw in KEYWORDS_RELEVANTES)


def obtener_noticias(max_por_feed: int = 6, solo_relevantes: bool = False,
                     log_fn=None) -> list:
    """
    Devuelve lista de noticias de todos los feeds.
      max_por_feed   → cuántos titulares traer de cada medio
      solo_relevantes→ si True, filtra por keywords de tu cartera
      log_fn         → función de log opcional (la del script principal)
    """
    def _log(msg, level="INFO"):
        if log_fn:
            log_fn(msg, level)

    todas = []
    for feed in FEEDS:
        _log(f"Noticias → {feed['medio']}...")
        if _FEEDPARSER:
            items = _parse_con_feedparser(feed["url"], feed["medio"], max_por_feed)
        else:
            items = _parse_manual(feed["url"], feed["medio"], max_por_feed)

        if items:
            _log(f"  {len(items)} titulares de {feed['medio']}", "OK")
        else:
            _log(f"  sin respuesta de {feed['medio']}", "WARN")
        todas.extend(items)

    # Marca relevancia y opcionalmente filtra
    for n in todas:
        n["relevante"] = _es_relevante(n)

    if solo_relevantes:
        todas = [n for n in todas if n["relevante"]]

    # Relevantes primero
    todas.sort(key=lambda n: not n["relevante"])
    return todas


# ═══════════════════════════════════════════════════════════
#  PRUEBA STANDALONE
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Prueba de noticias.py")
    print(f"feedparser disponible: {_FEEDPARSER}")
    print("=" * 50)
    noticias = obtener_noticias(max_por_feed=4, log_fn=lambda m, l="INFO": print(f"  [{l}] {m}"))
    print(f"\nTotal: {len(noticias)} noticias\n")
    for n in noticias[:10]:
        marca = "★" if n["relevante"] else " "
        print(f"{marca} [{n['medio']}] {n['titulo'][:70]}")
