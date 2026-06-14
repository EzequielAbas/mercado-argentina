"""
=============================================================
  FUENTE CAFCI — Cotización de Fondos Comunes de Inversión
  Cartera Inversor v6 | Ezequiel | junio 2026

  API pública CAFCI (sin auth). Funciona solo desde PC local
  (bloquea servidores externos igual que Bonistas).

  IDs verificados en https://api.cafci.org.ar/fondo
  (buscados con buscar_fondo() la primera vez)
=============================================================
"""

import datetime
import requests

BASE    = "https://api.cafci.org.ar"
TIMEOUT = 15
HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "es-AR,es;q=0.9",
    "Referer":         "https://cafci.org.ar/",
    "Origin":          "https://cafci.org.ar",
}

# ─────────────────────────────────────────────────────────────
# IDs de tus fondos en CAFCI
# Verificar / actualizar con buscar_fondo() si alguno cambia.
# Formato: ticker_cartera -> (fondo_id, clase_id, nombre_display)
# clase_id=None → toma la primera clase disponible
# ─────────────────────────────────────────────────────────────
FONDOS = {
    "_IOLPORA":    (595,  None, "IOL Portafolio Potenciado A"),
    "_IOLCAMA":    (596,  None, "IOL Cash Management A"),
    "_BCMMA":      (119,  None, "Balanz Capital Money Market A"),
    "_INSTITUA":   (118,  None, "Balanz Capital Inflation Linked A"),
    "_ICBC_AHORRO":(243,  None, "ICBC Alpha Ahorro A"),
    "_ICBC_RENTA": (244,  None, "ICBC Alpha Renta Capital A"),
}


def _get(path, params=None):
    try:
        r = requests.get(BASE + path, headers=HEADERS, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None  # silencioso — API requiere auth desde servidores externos


def _fecha_habil_anterior(n=1):
    d = datetime.date.today()
    count = 0
    while count < n:
        d -= datetime.timedelta(days=1)
        if d.weekday() < 5:
            count += 1
    return d.strftime("%Y-%m-%d")


def buscar_fondo(nombre, max_res=8):
    """Busca fondos por nombre. Útil para descubrir IDs de fondos nuevos."""
    data = _get("/fondo", {"estado": 1, "include": "gerente", "limit": "ALL"})
    if not data or "data" not in data:
        return []
    nombre_l = nombre.lower()
    out = []
    for f in data["data"]:
        fn = (f.get("nombre") or "").lower()
        ger = ((f.get("gerente") or {}).get("nombre") or "").lower()
        if any(tok in fn or tok in ger for tok in nombre_l.split()):
            out.append({
                "id":      f["id"],
                "nombre":  f.get("nombre"),
                "gerente": (f.get("gerente") or {}).get("nombre", "—"),
            })
        if len(out) >= max_res:
            break
    return out


def get_vcp(fondo_id, clase_id=None):
    """
    VCP (Valor de Cuotaparte) más reciente.
    Retrocede hasta 5 días hábiles si no hay dato en T-1.
    Devuelve dict {vcp, fecha, clase_id} o None.
    """
    for intento in range(5):
        fecha = _fecha_habil_anterior(intento + 1)
        data = _get(f"/fondo/{fondo_id}/cuotapartes", {
            "fechaDesde": fecha, "fechaHasta": fecha,
        })
        if not data or "data" not in data:
            continue
        registros = data["data"]
        if clase_id is not None:
            registros = [r for r in registros if r.get("clase_id") == clase_id]
        if not registros:
            continue
        r = registros[0]
        vcp = float(r.get("vcp") or r.get("valor") or 0)
        if vcp > 0:
            return {"vcp": vcp, "fecha": r.get("fecha", fecha), "clase_id": r.get("clase_id")}
    return None


def get_rendimiento(fondo_id, clase_id=None):
    """TNA, var 30d y YTD del fondo."""
    hoy   = datetime.date.today()
    desde = (hoy - datetime.timedelta(days=400)).strftime("%Y-%m-%d")
    hasta = hoy.strftime("%Y-%m-%d")
    data  = _get(f"/fondo/{fondo_id}/rendimiento", {"fechaDesde": desde, "fechaHasta": hasta})
    if not data or "data" not in data or not data["data"]:
        return None
    regs = data["data"]
    if clase_id is not None:
        regs = [r for r in regs if r.get("clase_id") == clase_id] or regs
    regs.sort(key=lambda r: r.get("fecha", ""))
    ult = regs[-1]
    return {
        "tna":    float(ult.get("tna")    or 0),
        "tea":    float(ult.get("tea")    or 0),
        "var_7d": float(ult.get("variacion7d")  or 0),
        "var_30d":float(ult.get("variacion30d") or 0),
        "var_ytd":float(ult.get("variacionYtd") or 0),
        "fecha":  ult.get("fecha"),
    }


def valorizar_fcis(cartera):
    """
    Recibe la lista CARTERA de integracion_v5 y devuelve dict con
    valorización actualizada de cada FCI.

    Devuelve:
      { "_BCMMA": { vcp, vcp_fecha, cantidad, valor_actual,
                    invertido, pnl, pnl_pct, tna, var_30d, var_ytd }, ... }
    """
    resultado = {}
    for pos in cartera:
        tk = pos.get("ticker", "")
        if not tk.startswith("_") or pos.get("tipo") != "fci":
            continue
        info = FONDOS.get(tk)
        if not info:
            continue
        fondo_id, clase_id, nombre_display = info
        cantidad  = pos.get("cantidad")
        invertido = pos.get("invertido", 0)

        vcp_data  = get_vcp(fondo_id, clase_id)
        rend_data = get_rendimiento(fondo_id, clase_id)

        if vcp_data and cantidad:
            vcp          = vcp_data["vcp"]
            valor_actual = round(vcp * cantidad, 2)
            pnl          = round(valor_actual - invertido, 2)
            pnl_pct      = round(pnl / invertido * 100, 2) if invertido else 0
        else:
            vcp = valor_actual = None
            pnl = pnl_pct = 0
            valor_actual = invertido  # fallback limpio

        resultado[tk] = {
            "nombre_display": nombre_display,
            "vcp":            vcp,
            "vcp_fecha":      vcp_data["fecha"] if vcp_data else None,
            "cantidad":       cantidad,
            "valor_actual":   valor_actual,
            "invertido":      invertido,
            "pnl":            pnl,
            "pnl_pct":        pnl_pct,
            "tna":            rend_data["tna"]    if rend_data else None,
            "var_30d":        rend_data["var_30d"] if rend_data else None,
            "var_ytd":        rend_data["var_ytd"] if rend_data else None,
        }
    return resultado


# ─────────────────────────────────────────────────────────────
# CLI de prueba (correr directamente: python fuente_cafci.py)
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Prueba CAFCI ===\n")
    print("Buscando 'Balanz Money Market'...")
    for r in buscar_fondo("Balanz Money Market", 3):
        print(f"  ID={r['id']} | {r['nombre']} | {r['gerente']}")

    print("\nVCP Balanz MM (id=119):")
    v = get_vcp(119)
    print(f"  {v}" if v else "  Sin datos")

    print("\nRendimiento Balanz MM (id=119):")
    rd = get_rendimiento(119)
    if rd:
        print(f"  TNA={rd['tna']:.2f}% | Var30d={rd['var_30d']:.2f}% | YTD={rd['var_ytd']:.2f}%")
