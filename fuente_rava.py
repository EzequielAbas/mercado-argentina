"""
=============================================================
  FUENTE RAVA — parser de cotizaciones argentinas
  Cartera Inversor v4 | Ezequiel | junio 2026

  Rava sirve el HTML con TODOS los datos ya renderizados en el
  servidor (no usa JS para cargar las tablas). Eso lo hace
  parseable directamente con BeautifulSoup — sin API.

  Da: dólar (MEP/CCL/oficial/mayorista), riesgo país, MERVAL,
  bonos (incl. TIR y duración), acciones, CEDEARs, etc.

  ⚠️ IMPORTANTE — uso responsable:
    - Rava NO ofrece API pública. Esto es scraping del HTML.
    - Sus términos de uso no autorizan scraping intensivo.
    - Para uso PERSONAL, baja frecuencia (1 vez al día), está
      en una zona gris aceptable. NO lo corras en loop ni cada
      minuto: te pueden banear la IP y además no corresponde.
    - Identificate con un User-Agent honesto y cacheá el
      resultado. El script ya lo hace.
    - Si en algún momento querés algo 100% limpio y legal,
      la fuente oficial es BYMA Data (otra integración).

  Dependencias:
    pip install requests beautifulsoup4 lxml
=============================================================
"""

import re
from pathlib import Path

try:
    import requests
    requests.packages.urllib3.disable_warnings()
except ImportError:
    raise SystemExit("[!] pip install requests")

try:
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit("[!] pip install beautifulsoup4 lxml")


BASE = "https://www.rava.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (CarteraInversor/4.0 uso personal; +contacto)",
    "Accept": "text/html,application/xhtml+xml",
}


def _num(texto: str):
    """Convierte número formato argentino '1.458,79' → 1458.79."""
    if texto is None:
        return None
    t = texto.strip().replace("\xa0", "").replace(" ", "")
    if t in ("", "-", "—"):
        return None
    # quitar separador de miles (.) y pasar coma decimal a punto
    t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _parse_tabla_por_titulo(soup, titulo_buscado: str) -> list:
    """
    Busca una tabla por el texto de su <span class="tabla-titulo-text">
    y devuelve sus filas como lista de dicts {especie, ultimo, ...}.
    """
    for bloque in soup.find_all("div", class_="tabla-home"):
        tit = bloque.find("span", class_="tabla-titulo-text")
        if not tit or titulo_buscado.lower() not in tit.get_text(strip=True).lower():
            continue
        # primera tabla visible del bloque
        tabla = bloque.find("table")
        if not tabla:
            continue
        return _filas_de_tabla(tabla)
    return []


def _filas_de_tabla(tabla) -> list:
    filas = []
    tbody = tabla.find("tbody") or tabla
    for tr in tbody.find_all("tr"):
        esp_cell = tr.find("td", class_="td-especie")
        if not esp_cell:
            continue
        b = esp_cell.find("b")
        especie = b.get_text(strip=True) if b else esp_cell.get_text(strip=True)
        celdas = tr.find_all("td", class_="td-right")
        valores = [_num(c.get_text()) for c in celdas]
        filas.append({"especie": especie, "valores": valores})
    return filas


# ═══════════════════════════════════════════════════════════
#  API PÚBLICA DEL MÓDULO
# ═══════════════════════════════════════════════════════════

def parse_home(html: str) -> dict:
    """
    Parsea el HTML de la home de Rava y extrae lo más útil:
    dólares, riesgo país, MERVAL. Devuelve dict estructurado.
    """
    soup = BeautifulSoup(html, "lxml")

    out = {"dolares": {}, "riesgo_pais": None, "merval": None}

    # ── Dólares ──
    for f in _parse_tabla_por_titulo(soup, "Dólar"):
        if f["valores"]:
            out["dolares"][f["especie"]] = {
                "ultimo": f["valores"][0],
                "var_dia": f["valores"][1] if len(f["valores"]) > 1 else None,
            }

    # ── Riesgo país ──
    rp = _parse_tabla_por_titulo(soup, "Riesgo")
    if rp and rp[0]["valores"]:
        out["riesgo_pais"] = {
            "valor": rp[0]["valores"][0],
            "var_dia": rp[0]["valores"][1] if len(rp[0]["valores"]) > 1 else None,
        }

    # ── MERVAL ──
    mv = _parse_tabla_por_titulo(soup, "Merval")
    if mv and mv[0]["valores"]:
        out["merval"] = {"valor": mv[0]["valores"][0]}

    return out


def get_home() -> dict | None:
    """Descarga la home de Rava y la parsea. Para uso real."""
    try:
        r = requests.get(BASE + "/", headers=HEADERS, timeout=12, verify=False)
        r.raise_for_status()
        return parse_home(r.text)
    except Exception:
        return None


def extraer_historico_perfil(html: str):
    """
    Extrae el histórico OHLCV embebido en la página de perfil de Rava.

    El perfil incluye un array JS `_chartData = [{...}]` (y otro idéntico
    en downloadCotiHistCSV) con ~65 ruedas: apertura, maximo, minimo,
    cierre, volumen, fecha. Devuelve un DataFrame con columnas
    date/open/high/low/close/volume compatible con analisis_tecnico.analizar().

    Devuelve None si no encuentra el array o si pandas no está disponible.
    """
    import json
    try:
        import pandas as pd
    except ImportError:
        return None

    # Array de objetos que empieza con {"especie": ...}
    # (descarta el intradiario, que empieza con {"ultimo":...})
    m = re.search(r'(\[\{"especie".*?\}\])\s*;', html, re.DOTALL)
    if not m:
        return None
    try:
        registros = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if not registros:
        return None

    filas = []
    for d in registros:
        cierre = d.get("cierre") or d.get("ultimo")
        if cierre is None:
            continue
        filas.append({
            "date":   d.get("fecha"),
            "open":   d.get("apertura") or cierre,
            "high":   d.get("maximo") or cierre,
            "low":    d.get("minimo") or cierre,
            "close":  cierre,
            "volume": d.get("volumen") or 0,
        })
    if not filas:
        return None

    df = pd.DataFrame(filas)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    return df


def get_perfil_historico(simbolo: str):
    """
    Descarga la página de perfil de Rava y devuelve el histórico OHLCV
    como DataFrame. Fuente PRIMARIA de histórico para análisis técnico
    de instrumentos argentinos.

    URL: https://www.rava.com/perfil/AO27
    """
    try:
        url = f"{BASE}/perfil/{simbolo.upper()}"
        r = requests.get(url, headers=HEADERS, timeout=12, verify=False)
        r.raise_for_status()
        return extraer_historico_perfil(r.text)
    except Exception:
        return None


if __name__ == "__main__":
    # Prueba contra el fixture (HTML real pegado por Ezequiel)
    fixture = Path(__file__).parent / "_fixture_rava.html"
    if fixture.exists():
        data = parse_home(fixture.read_text(encoding="utf-8"))
        import json
        print(json.dumps(data, ensure_ascii=False, indent=2))
