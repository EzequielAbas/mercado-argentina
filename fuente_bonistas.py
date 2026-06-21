"""
fuente_bonistas.py v2 — Conector para datos de Bonistas.com
Actualizado con estructura real del JSON observado (06/06/2026).

APIs cubiertas:
  - /api/bonds          → todos los bonos (soberanos, CER, LECAP, ONs, CEDEARs, etc.)
  - /api/fx/fx          → MEP/Cable implícito por instrumento
  - /api/curves         → curvas de rendimiento por familia
  - /api/market-status  → estado del mercado

Notas de la API real:
  - CEDEARs tienen bond_family="" (se filtran con exclude_cedears=True)
  - performing=False → no operó hoy (last_price=0)
  - Algunos bonos vienen duplicados (CI y 24hs), filtrar por settlement
  - mep=1 en bonos ARS significa que no tienen precio USD implícito
  - Dollar Linked tienen tc_value / tc_t0 con tipo de cambio oficial
"""

import requests
import pandas as pd
from datetime import datetime

BASE_URL = "https://bonistas.com"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://bonistas.com/",
}

TIMEOUT = 15

# ─────────────────────────────────────────────────────────────
# Mapa de familias con labels amigables
# ─────────────────────────────────────────────────────────────
FAMILIAS_LABEL = {
    "BONO-USD-LPA":       "Soberanos USD Ley Arg. (en $)",
    "BONO-USD-LDA":       "Soberanos USD Ley Arg. (en USD MEP)",
    "BONO-USD-LCA":       "Soberanos USD Ley Arg. (Cable)",
    "BONO-USD-LPNY":      "Soberanos USD Ley NY (en $)",
    "BONO-USD-LDNY":      "Soberanos USD Ley NY (en USD MEP)",
    "BONO-USD-LCNY":      "Soberanos USD Ley NY (Cable)",
    "BONO-CER":           "Bonos CER (ajuste inflación)",
    "LETRAS-CER":         "Letras CER (LECER)",
    "BONO-FIJA":          "Bonos Tasa Fija ARS",
    "LETRAS-FIJO":        "Letras Tasa Fija (LECAP)",
    "LETRAS-FIJO-USD":    "Letras Tasa Fija (en USD)",
    "DOLAR-LINKED":       "Dollar Linked",
    "BONO-TAMAR":         "Bonos TAMAR",
    "DUAL":               "Bonos Duales (Fija/TAMAR)",
    "BONO-DUAL-TAMAR":    "Duales Tasa TAMAR",
    "BONO-BADLAR":        "Bonos BADLAR",
    "BOPREAL":            "BOPREALes (en USD D)",
    "BOPREAL-CABLE":      "BOPREALes (Cable)",
    "BOPREAL-PESOS":      "BOPREALes (en $)",
    "ONS":                "ONs YPF (en USD)",
    "ONS-CABLE":          "ONs YPF (Cable)",
}

# Familias que conforman los bonos soberanos USD principales
FAMILIAS_SOBERANOS_USD = [
    "BONO-USD-LPA", "BONO-USD-LPNY",
    "BONO-USD-LDA", "BONO-USD-LDNY",
]


# ─────────────────────────────────────────────────────────────
# Helper HTTP
# ─────────────────────────────────────────────────────────────

def _get(path: str, params: dict = None):
    url = BASE_URL + path
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[Bonistas] ERROR {path}: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# Helpers de formato
# ─────────────────────────────────────────────────────────────

def _pct(val) -> str:
    try:
        v = float(val)
        if abs(v) > 10:   # probablemente ya es porcentaje
            return f"{v:.2f}%"
        return f"{v * 100:.2f}%"
    except:
        return "—"

def _fmt(val, decimals=2) -> str:
    try:
        return f"{float(val):,.{decimals}f}"
    except:
        return "—"

def _date(val) -> str:
    if not val:
        return "—"
    return str(val)[:10]


# ─────────────────────────────────────────────────────────────
# Market Status
# ─────────────────────────────────────────────────────────────

def get_market_status() -> dict:
    """
    Devuelve estado del mercado.
    {'is_open': bool, 'current_time': '17:00', 'market_hours': '10:30-17:00'}
    """
    data = _get("/api/market-status")
    if not data:
        return {"is_open": False, "current_time": "—", "market_hours": "10:30-17:00"}
    return data


# ─────────────────────────────────────────────────────────────
# FX Implícito
# ─────────────────────────────────────────────────────────────

def get_fx() -> pd.DataFrame:
    """
    Retorna DataFrame con FX implícito MEP/Cable por instrumento.
    Columnas clave: ticker, name, settlement, mep_last, cable, mep_var, price_ars, price_usd
    """
    data = _get("/api/fx/fx")
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    if "name" in df.columns:
        df = df.sort_values("name").reset_index(drop=True)
    return df


def get_fx_summary(df_fx: pd.DataFrame = None) -> dict:
    """
    Dict con MEP y Cable de referencia.
    Prioriza AL30 24hs como referencia principal.
    """
    if df_fx is None:
        df_fx = get_fx()
    if df_fx.empty:
        return {"mep_avg": 0, "cable_avg": 0, "mep_al30": 0, "cable_al30": 0}

    summary = {}
    try:
        df_24 = df_fx[df_fx.get("settlement", pd.Series()) == "24hs"] if "settlement" in df_fx.columns else df_fx
        if df_24.empty:
            df_24 = df_fx

        mep_vals = pd.to_numeric(df_24.get("mep_last", pd.Series()), errors="coerce").dropna()
        cable_vals = pd.to_numeric(df_24.get("cable", pd.Series()), errors="coerce").dropna()
        mep_vals = mep_vals[mep_vals > 100]   # filtra valores sin precio (mep=0 o mep=1)
        cable_vals = cable_vals[cable_vals > 100]

        summary["mep_avg"] = float(mep_vals.mean()) if not mep_vals.empty else 0
        summary["cable_avg"] = float(cable_vals.mean()) if not cable_vals.empty else 0

        # AL30 como referencia
        row_al30 = df_24[df_24["ticker"].str.contains("AL30", na=False)] if "ticker" in df_24.columns else pd.DataFrame()
        if not row_al30.empty:
            summary["mep_al30"] = float(row_al30.iloc[0].get("mep_last", 0))
            summary["cable_al30"] = float(row_al30.iloc[0].get("cable", 0))
        else:
            summary["mep_al30"] = summary["mep_avg"]
            summary["cable_al30"] = summary["cable_avg"]
    except Exception as e:
        print(f"[Bonistas] get_fx_summary error: {e}")

    return summary


# ─────────────────────────────────────────────────────────────
# Bonds — función principal
# ─────────────────────────────────────────────────────────────

def get_bonds(
    performing_only: bool = True,
    families: list = None,
    exclude_cedears: bool = True,
    settlement: str = None,
    deduplicate: bool = True,
) -> pd.DataFrame:
    """
    Descarga /api/bonds y retorna DataFrame limpio.

    Args:
        performing_only:  excluye bonos sin precio hoy (performing=False)
        families:         lista de bond_family a incluir (None = todas)
        exclude_cedears:  excluye CEDEARs (bond_family == "")
        settlement:       "CI", "24hs" o None (ambos)
        deduplicate:      si True, cuando hay CI y 24hs del mismo ticker, 
                          prefiere 24hs (mayor liquidez)
    """
    data = _get("/api/bonds")
    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)

    # Excluir CEDEARs (bond_family vacío)
    if exclude_cedears:
        df = df[df["bond_family"].astype(str).str.strip() != ""]

    # Solo los que operaron hoy
    if performing_only:
        if "performing" in df.columns:
            df = df[df["performing"] == True]
        if "last_price" in df.columns:
            df = df[pd.to_numeric(df["last_price"], errors="coerce") > 0]

    # Filtrar por familia
    if families:
        df = df[df["bond_family"].isin(families)]

    # Filtrar por settlement
    if settlement and "settlement" in df.columns:
        df = df[df["settlement"] == settlement]

    # Deduplicar: si el mismo ticker aparece en CI y 24hs, quedarse con 24hs
    if deduplicate and "ticker" in df.columns and "settlement" in df.columns:
        # Ordenar: 24hs primero
        df = df.copy()
        df["_settle_prio"] = df["settlement"].map({"24hs": 0, "CI": 1}).fillna(2)
        df = df.sort_values(["ticker", "_settle_prio"])
        df = df.drop_duplicates(subset=["ticker"], keep="first")
        df = df.drop(columns=["_settle_prio"])

    # Columnas útiles
    cols = [
        "ticker", "bond_family", "bond_family_label", "bond_law",
        "short_description", "index",
        "last_price", "last_close", "day_difference",
        "tir", "tna", "modified_duration",
        "parity", "coupon", "coupon_yield",
        "end_date", "start_date", "days_to_finish",
        "settlement", "mep", "volume",
        "performing",
        # Dollar linked extras
        "tc_value", "tc_t0", "tc_t3",
    ]
    cols_exist = [c for c in cols if c in df.columns]
    df = df[cols_exist].copy()

    # Convertir numéricos
    num_cols = [
        "tir", "tna", "modified_duration", "parity",
        "last_price", "last_close", "day_difference",
        "mep", "volume", "coupon", "coupon_yield",
        "tc_value", "tc_t0", "tc_t3", "days_to_finish",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.sort_values(
        ["bond_family", "days_to_finish"] if "days_to_finish" in df.columns
        else ["bond_family", "ticker"]
    ).reset_index(drop=True)

    return df


def get_bonds_by_family(df: pd.DataFrame = None) -> dict:
    """Agrupa el DataFrame de bonos por bond_family."""
    if df is None:
        df = get_bonds()
    if df.empty:
        return {}
    return {fam: grp.reset_index(drop=True) for fam, grp in df.groupby("bond_family")}


def get_soberanos_usd(df: pd.DataFrame = None) -> pd.DataFrame:
    """Devuelve soberanos USD más líquidos (AL29/30/35/38/41, GD29/30/35/38/41/46)."""
    if df is None:
        df = get_bonds()
    if df.empty:
        return pd.DataFrame()
    # Preferimos la versión en pesos (LPA/LPNY) para ver el MEP implícito
    return df[df["bond_family"].isin(FAMILIAS_SOBERANOS_USD)].copy()


# ─────────────────────────────────────────────────────────────
# Curves
# ─────────────────────────────────────────────────────────────

def get_curves(settlement: str = "24hs") -> dict:
    """
    Descarga /api/curves.
    Retorna dict { familia: DataFrame(ticker, modified_duration, tir) }.
    Nota: las curvas CI suelen venir vacías; usar settlement='24hs'.
    """
    data = _get("/api/curves")
    if not data:
        return {}

    prefix = f"CURVE_{settlement}_"
    result = {}
    for key, items in data.items():
        if not key.startswith(prefix):
            continue
        familia = key[len(prefix):]
        if not items:
            continue
        df = pd.DataFrame(items)
        if df.empty or "modified_duration" not in df.columns:
            continue
        df = df[pd.to_numeric(df["modified_duration"], errors="coerce") > 0].copy()
        df["modified_duration"] = pd.to_numeric(df["modified_duration"], errors="coerce")
        df["tir"] = pd.to_numeric(df.get("tir", pd.Series()), errors="coerce")
        df = df.sort_values("modified_duration").reset_index(drop=True)
        if not df.empty:
            result[familia] = df

    return result


# ─────────────────────────────────────────────────────────────
# HTML helpers
# ─────────────────────────────────────────────────────────────

def bonds_to_html_table(df: pd.DataFrame, max_rows: int = 20, show_mep: bool = False,
                        cartera_tickers: set | None = None, sort_by_tir: bool = False) -> str:
    """Convierte DataFrame de bonos en tabla HTML. show_mep muestra columna MEP implícito."""
    if df.empty:
        return "<p style='color:#888;font-size:12px'>Sin datos disponibles</p>"

    if sort_by_tir and "tir" in df.columns:
        df = df.copy()
        df["_tir_abs"] = df["tir"].abs()
        df = df.sort_values("_tir_abs", ascending=False).drop(columns=["_tir_abs"])

    cartera_tickers = cartera_tickers or set()
    shown = df.head(max_rows)
    extra_en_cartera = []
    if cartera_tickers:
        shown_tickers = set(shown["ticker"].values)
        for tk in cartera_tickers:
            if tk not in shown_tickers:
                match = df[df["ticker"] == tk]
                if not match.empty:
                    extra_en_cartera.append(match.iloc[0])

    extra_header = "<th>MEP impl.</th>" if show_mep else ""
    rows_html = ""
    for _, r in pd.concat([shown, pd.DataFrame(extra_en_cartera)]).iterrows():
        tir_val  = r.get("tir", None)
        tna_val  = r.get("tna", None)
        dur_val  = r.get("modified_duration", None)
        par_val  = r.get("parity", None)
        day_d    = r.get("day_difference", 0) or 0
        price    = r.get("last_price", 0)
        mep_val  = r.get("mep", 0)
        end_date = _date(r.get("end_date"))
        ticker   = r.get("ticker", "—")
        settle   = r.get("settlement", "—")
        index    = r.get("index", "")

        tir_str = _pct(tir_val)  if (tir_val and tir_val != 0) else "—"
        tna_str = _pct(tna_val)  if (tna_val and tna_val != 0) else "—"
        dur_str = _fmt(dur_val)  if dur_val else "—"
        par_str = _pct(par_val)  if par_val else "—"

        # Precio: si es ARS grande, formatearlo diferente
        if price > 1000:
            price_str = f"${price:,.0f}"
        else:
            price_str = f"{price:,.2f}"

        day_color = "#27ae60" if day_d >= 0 else "#e74c3c"
        day_str = f"{day_d * 100:+.2f}%" if day_d else "—"

        mep_cell = f"<td>{_fmt(mep_val)}</td>" if show_mep and mep_val and mep_val > 100 else ("<td>—</td>" if show_mep else "")

        # Color de fondo según tipo
        bg = ""
        if index == "CER":
            bg = "background:#fef9e7"
        elif index == "USS":
            bg = "background:#eaf4fb"
        elif index == "USDL":
            bg = "background:#e9f7ef"

        cartera_badge = ' <span style="font-size:8px;background:#00d4aa;color:#000;padding:1px 4px;border-radius:3px;vertical-align:middle">EN CARTERA</span>' if ticker in cartera_tickers else ""

        rows_html += f"""
        <tr style="{bg}">
          <td><b style="font-size:11px">{ticker}</b>{cartera_badge}</td>
          <td style="text-align:right">{price_str}</td>
          <td style="color:{day_color};text-align:right">{day_str}</td>
          <td style="text-align:right">{tir_str}</td>
          <td style="text-align:right">{dur_str}</td>
          <td style="text-align:right">{par_str}</td>
          <td>{end_date}</td>
          <td style="font-size:10px;color:#888">{settle}</td>
          {mep_cell}
        </tr>"""

    extra_col = "<th>MEP</th>" if show_mep else ""
    return f"""
    <table style="width:100%;border-collapse:collapse;font-size:11px;margin-top:6px">
      <thead>
        <tr style="background:#2c3e50;color:#fff;font-size:11px">
          <th style="padding:5px;text-align:left">Ticker</th>
          <th style="text-align:right">Precio</th>
          <th style="text-align:right">Var%</th>
          <th style="text-align:right">TIR/TEM</th>
          <th style="text-align:right">Duration</th>
          <th style="text-align:right">Paridad</th>
          <th>Vto</th>
          <th>Liquid</th>
          {extra_col}
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>"""


def fx_to_html_table(df_fx: pd.DataFrame, max_rows: int = 12) -> str:
    """Tabla HTML del FX implícito."""
    if df_fx.empty:
        return "<p style='color:#888;font-size:12px'>Sin datos FX</p>"

    rows_html = ""
    for _, r in df_fx.head(max_rows).iterrows():
        ticker = r.get("ticker", "—")
        name   = r.get("name", "—")
        settle = r.get("settlement", "—")
        mep    = r.get("mep_last", 0)
        cable  = r.get("cable", 0)
        var    = r.get("mep_var", 0) or 0

        if not mep or mep < 100:
            continue  # sin precio

        var_color = "#27ae60" if var >= 0 else "#e74c3c"
        var_str   = f"{var * 100:+.2f}%"

        rows_html += f"""
        <tr>
          <td><b>{ticker}</b></td>
          <td style="color:#555">{name}</td>
          <td style="font-size:10px;color:#888">{settle}</td>
          <td style="font-weight:bold;color:#1a5276;text-align:right">${_fmt(mep)}</td>
          <td style="color:#117a65;text-align:right">${_fmt(cable)}</td>
          <td style="color:{var_color};text-align:right">{var_str}</td>
        </tr>"""

    if not rows_html:
        return "<p style='color:#888;font-size:12px'>Sin datos FX hoy</p>"

    return f"""
    <table style="width:100%;border-collapse:collapse;font-size:11px;margin-top:6px">
      <thead>
        <tr style="background:#1a5276;color:#fff">
          <th style="padding:5px;text-align:left">Ticker</th>
          <th>Instrumento</th>
          <th>Liquid.</th>
          <th style="text-align:right">MEP impl.</th>
          <th style="text-align:right">Cable impl.</th>
          <th style="text-align:right">Var MEP</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>"""


def get_panel_bonistas_html(cartera_tickers: set | None = None) -> str:
    """
    Genera el panel completo de Bonistas para insertar en el reporte HTML.
    Incluye: market status, FX, soberanos, CER, LECAP.
    """
    # ── Market Status ──────────────────────────────────────────
    status  = get_market_status()
    is_open = status.get("is_open", False)
    hora    = status.get("current_time", "—")
    horario = status.get("market_hours", "10:30-17:00")
    estado_str   = "🟢 ABIERTO" if is_open else "🔴 CERRADO"
    estado_color = "#27ae60"   if is_open else "#e74c3c"

    # ── FX ─────────────────────────────────────────────────────
    df_fx    = get_fx()
    fx_sum   = get_fx_summary(df_fx)
    mep_al30 = _fmt(fx_sum.get("mep_al30",  fx_sum.get("mep_avg", 0)))
    cab_al30 = _fmt(fx_sum.get("cable_al30", fx_sum.get("cable_avg", 0)))
    mep_avg  = _fmt(fx_sum.get("mep_avg",   0))
    cab_avg  = _fmt(fx_sum.get("cable_avg", 0))

    # ── Bonds ──────────────────────────────────────────────────
    df_all = get_bonds(performing_only=True, exclude_cedears=True, deduplicate=True)

    df_sov = pd.DataFrame()
    df_cer = pd.DataFrame()
    df_fija = pd.DataFrame()
    df_ons  = pd.DataFrame()

    if not df_all.empty:
        df_sov  = df_all[df_all["bond_family"].isin(FAMILIAS_SOBERANOS_USD)].copy()
        df_cer  = df_all[df_all["bond_family"].isin(["BONO-CER", "LETRAS-CER"])].copy()
        df_fija = df_all[df_all["bond_family"].isin(["LETRAS-FIJO", "BONO-FIJA"])].copy()
        df_ons  = df_all[df_all["bond_family"].isin(["ONS"])].copy()

    _ct = cartera_tickers or set()
    tabla_fx   = fx_to_html_table(df_fx, max_rows=4)
    tabla_sov  = bonds_to_html_table(df_sov,  max_rows=4, cartera_tickers=_ct, sort_by_tir=True)
    tabla_cer  = bonds_to_html_table(df_cer,  max_rows=4, cartera_tickers=_ct, sort_by_tir=True)
    tabla_fija = bonds_to_html_table(df_fija, max_rows=4, cartera_tickers=_ct, sort_by_tir=True)
    tabla_ons  = bonds_to_html_table(df_ons,  max_rows=4, cartera_tickers=_ct, sort_by_tir=True)

    ts = datetime.now().strftime("%d/%m/%Y %H:%M")

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:1200px;margin:0 auto;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1a5276,#2980b9);color:#fff;
              padding:14px 20px;border-radius:8px 8px 0 0;margin-top:20px">
    <h2 style="margin:0;font-size:17px">📊 Mercado de Bonos — Bonistas.com</h2>
    <span style="font-size:11px;opacity:0.8">Datos: {ts}</span>
  </div>

  <!-- KPIs: status + FX -->
  <div style="background:#eaf4fb;padding:12px 20px;display:flex;gap:28px;
              flex-wrap:wrap;border:1px solid #aed6f1;border-top:none">
    <div>
      <div style="font-size:11px;color:#666">Mercado</div>
      <div style="font-size:17px;font-weight:bold;color:{estado_color}">{estado_str}</div>
      <div style="font-size:10px;color:#888">{hora} | {horario}</div>
    </div>
    <div>
      <div style="font-size:11px;color:#666">MEP implícito (AL30)</div>
      <div style="font-size:20px;font-weight:bold;color:#1a5276">$ {mep_al30}</div>
    </div>
    <div>
      <div style="font-size:11px;color:#666">Cable implícito (AL30)</div>
      <div style="font-size:20px;font-weight:bold;color:#117a65">$ {cab_al30}</div>
    </div>
    <div>
      <div style="font-size:11px;color:#666">MEP promedio bonos</div>
      <div style="font-size:17px;font-weight:bold;color:#1a5276">$ {mep_avg}</div>
    </div>
    <div>
      <div style="font-size:11px;color:#666">Cable promedio bonos</div>
      <div style="font-size:17px;font-weight:bold;color:#117a65">$ {cab_avg}</div>
    </div>
  </div>

  <!-- FX por instrumento -->
  <div style="background:#fff;padding:14px 20px;border:1px solid #aed6f1;border-top:none">
    <h3 style="margin:0 0 8px;font-size:13px;color:#1a5276">💱 FX Implícito por Instrumento</h3>
    {tabla_fx}
  </div>

  <!-- Soberanos USD -->
  <div style="background:#fff;padding:14px 20px;border:1px solid #aed6f1;border-top:none">
    <h3 style="margin:0 0 8px;font-size:13px;color:#1a5276">🇺🇸 Bonos Soberanos USD (AL / GD)</h3>
    {tabla_sov}
  </div>

  <!-- Bonos CER -->
  <div style="background:#fff;padding:14px 20px;border:1px solid #aed6f1;border-top:none">
    <h3 style="margin:0 0 8px;font-size:13px;color:#6d4c41">📈 Bonos CER / LECER</h3>
    {tabla_cer}
  </div>

  <!-- LECAP / Tasa Fija -->
  <div style="background:#fff;padding:14px 20px;border:1px solid #aed6f1;border-top:none">
    <h3 style="margin:0 0 8px;font-size:13px;color:#4a235a">🏛️ LECAP / Bonos Tasa Fija ARS</h3>
    {tabla_fija}
  </div>

  <!-- ONs YPF -->
  <div style="background:#fff;padding:14px 20px;border:1px solid #aed6f1;
              border-top:none;border-radius:0 0 8px 8px">
    <h3 style="margin:0 0 8px;font-size:13px;color:#1b2631">🛢️ ONs YPF</h3>
    {tabla_ons}
  </div>

</div>
"""
    return html


# ─────────────────────────────────────────────────────────────
# CLI de prueba
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Market Status ===")
    ms = get_market_status()
    print(ms)

    print("\n=== FX Implícito (primeros 6) ===")
    df_fx = get_fx()
    if not df_fx.empty:
        cols_fx = [c for c in ["ticker", "name", "settlement", "mep_last", "cable", "mep_var"] if c in df_fx.columns]
        print(df_fx[cols_fx].head(6).to_string(index=False))
    else:
        print("Sin datos FX")

    print("\n=== FX Summary ===")
    print(get_fx_summary(df_fx))

    print("\n=== Soberanos USD (AL/GD en pesos, primeros 10) ===")
    df_b = get_bonds(families=FAMILIAS_SOBERANOS_USD, deduplicate=True)
    if not df_b.empty:
        show = ["ticker", "settlement", "last_price", "tir", "modified_duration", "parity", "end_date"]
        show = [c for c in show if c in df_b.columns]
        print(df_b[show].head(10).to_string(index=False))
    else:
        print("Sin datos bonos")

    print("\n=== CER (primeros 8) ===")
    df_cer = get_bonds(families=["BONO-CER", "LETRAS-CER"], deduplicate=True)
    if not df_cer.empty:
        show = ["ticker", "last_price", "tir", "modified_duration", "parity", "end_date"]
        show = [c for c in show if c in df_cer.columns]
        print(df_cer[show].head(8).to_string(index=False))

    print("\n=== LECAP / Fija (primeros 6) ===")
    df_fija = get_bonds(families=["LETRAS-FIJO", "BONO-FIJA"], deduplicate=True)
    if not df_fija.empty:
        show = ["ticker", "last_price", "tir", "modified_duration", "end_date"]
        show = [c for c in show if c in df_fija.columns]
        print(df_fija[show].head(6).to_string(index=False))

    print("\n=== Curves (24hs) — familias disponibles ===")
    curves = get_curves("24hs")
    print(list(curves.keys())[:10])

    print("\nDone.")
