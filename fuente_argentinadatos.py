"""
fuente_argentinadatos.py — Datos macro y de renta fija desde ArgentinaDatos.

API pública, gratuita, sin autenticación: https://api.argentinadatos.com
NO hace falta hostear el repo: se consume la URL directamente.

Reemplaza buena parte del scraping de Bonistas para el panel macro y renta fija.
Pensado para tener la misma forma de uso que tus otros fuente_*.py.

Smoke test:  python fuente_argentinadatos.py
"""

import requests

BASE = "https://api.argentinadatos.com"
TIMEOUT = 12

# Mapeo de la "casa" de ArgentinaDatos → tus etiquetas del panel macro
_CASA = {"oficial": "oficial", "blue": "blue", "bolsa": "mep", "contadoconliqui": "ccl"}


def _get(path):
    """GET con manejo de errores. Devuelve el JSON, o None si falla (no rompe el reporte)."""
    try:
        r = requests.get(f"{BASE}{path}", timeout=TIMEOUT,
                         headers={"Accept": "application/json"})
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  [argentinadatos] error en {path}: {e}")
        return None


def get_dolares():
    """
    Cotizaciones del dólar. Devuelve dict:
        {"mep": {"compra":.., "venta":.., "fecha":..}, "ccl": {...}, "oficial": {...}, "blue": {...}}
    """
    data = _get("/v1/dolares")
    out = {}
    if not data:
        return out
    for item in data:
        clave = _CASA.get(item.get("casa"))
        if clave:
            out[clave] = {
                "compra": item.get("compra"),
                "venta": item.get("venta"),
                "fecha": item.get("fecha"),
            }
    return out


def get_riesgo_pais():
    """Último valor del riesgo país (en puntos básicos). Devuelve dict {valor, fecha} o None."""
    data = _get("/v1/finanzas/indices/riesgo-pais/ultimo")
    if isinstance(data, dict):
        return {"valor": data.get("valor"), "fecha": data.get("fecha")}
    return None


def get_letras():
    """LECAP / LECER (tasa fija + CER). Lista de dicts tal cual los devuelve la API. Best-effort."""
    return _get("/v1/finanzas/letras") or []


def get_bonos_cer():
    """Bonos CER. Lista de dicts. Best-effort (verificá el path en la doc si cambia)."""
    return _get("/v1/finanzas/bonos-cer") or []


def get_fci(tipo="mercadoDinero"):
    """
    FCIs por tipo, con cuotaparte (vcp). tipo ∈ {mercadoDinero, rentaFija, rentaVariable, rentaMixta}.
    Sirve para valuar tus FCIs sin cargar el valorizado a mano (matcheá por 'fondo').
    """
    return _get(f"/v1/finanzas/fci/{tipo}/ultimo") or []


def buscar_fci(nombre_parcial, tipo="mercadoDinero"):
    """Devuelve el primer FCI cuyo nombre/fondo contenga `nombre_parcial` (case-insensitive)."""
    objetivo = nombre_parcial.lower()
    for f in get_fci(tipo):
        nombre = str(f.get("fondo") or f.get("nombre") or "").lower()
        if objetivo in nombre:
            return f
    return None


def get_feriados(anio):
    """Feriados del año (para el calendario financiero). Lista de dicts."""
    return _get(f"/v1/feriados/{anio}") or []


def get_macro():
    """Atajo: todo lo del panel MACRO en un solo dict."""
    dol = get_dolares()
    rp = get_riesgo_pais()
    return {
        "mep": dol.get("mep", {}).get("venta"),
        "ccl": dol.get("ccl", {}).get("venta"),
        "oficial": dol.get("oficial", {}).get("venta"),
        "blue": dol.get("blue", {}).get("venta"),
        "riesgo_pais": rp.get("valor") if rp else None,
        "fecha": rp.get("fecha") if rp else None,
    }


if __name__ == "__main__":
    print("== MACRO ==")
    m = get_macro()
    for k, v in m.items():
        print(f"  {k:12}: {v}")
    print("\n== Riesgo país ==", get_riesgo_pais())
    print("== Letras (primeras 3) ==")
    for x in get_letras()[:3]:
        print("  ", x)
    print("== FCI Money Market (primeros 3) ==")
    for x in get_fci("mercadoDinero")[:3]:
        print("  ", x)
