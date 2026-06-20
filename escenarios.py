"""
escenarios.py — Stress testing y analisis de escenarios para cartera argentina

Define escenarios macroeconomicos y estima el impacto en cada tipo de activo
usando modified_duration (para bonos) y sensibilidades estimadas (para otros).

La formula clave para bonos:
  cambio_precio % = -modified_duration * cambio_tasa

Dependencias: pandas, numpy (ya instaladas)
"""

import numpy as np

ESCENARIOS = [
    {
        "nombre": "Base (sin cambios)",
        "emoji": "➡️",
        "descripcion": "Mercado estable, sin shocks",
        "tasa_cambio_pp": 0,
        "mep_cambio_pct": 0,
        "inflacion_cambio_pp": 0,
        "riesgo_pais_bp": 0,
    },
    {
        "nombre": "Compresion riesgo pais",
        "emoji": "📈",
        "descripcion": "Mejora fiscal, ingreso capitales, bonos USD suben",
        "tasa_cambio_pp": -2,
        "mep_cambio_pct": -5,
        "inflacion_cambio_pp": -2,
        "riesgo_pais_bp": -200,
    },
    {
        "nombre": "Shock cambiario",
        "emoji": "💥",
        "descripcion": "Salto del dolar MEP 20%, tasas suben",
        "tasa_cambio_pp": 5,
        "mep_cambio_pct": 20,
        "inflacion_cambio_pp": 5,
        "riesgo_pais_bp": 300,
    },
    {
        "nombre": "Inflacion persistente",
        "emoji": "🔥",
        "descripcion": "Inflacion sube, CER se beneficia, tasa fija pierde",
        "tasa_cambio_pp": 3,
        "mep_cambio_pct": 10,
        "inflacion_cambio_pp": 8,
        "riesgo_pais_bp": 100,
    },
    {
        "nombre": "Recesion / flight to quality",
        "emoji": "📉",
        "descripcion": "Baja actividad, equity cae, bonos soberanos suben",
        "tasa_cambio_pp": -3,
        "mep_cambio_pct": 5,
        "inflacion_cambio_pp": -1,
        "riesgo_pais_bp": 50,
    },
]


def _sensibilidad_por_tipo(tipo: str) -> dict:
    """
    Devuelve coeficientes de sensibilidad para cada tipo de activo.
    Son aproximaciones simplificadas, no modelos precisos.
    """
    sensibilidades = {
        "bono_usd": {"tasa": -1.0, "mep": 0.3, "inflacion": 0, "riesgo": -0.02},
        "bono_cer": {"tasa": -0.3, "mep": 0.1, "inflacion": 0.8, "riesgo": -0.005},
        "bono_fija": {"tasa": -0.5, "mep": 0, "inflacion": -0.5, "riesgo": 0},
        "fci": {"tasa": 0.1, "mep": 0, "inflacion": 0, "riesgo": 0},
        "cedear": {"tasa": -0.2, "mep": 0.8, "inflacion": 0, "riesgo": -0.01},
    }
    return sensibilidades.get(tipo, {"tasa": 0, "mep": 0, "inflacion": 0, "riesgo": 0})


def aplicar_escenario(cartera: list, escenario: dict,
                      duraciones: dict = None) -> dict:
    """
    Estima el impacto de un escenario sobre cada posicion de la cartera.

    Parametros:
      cartera: lista de dicts con 'ticker', 'tipo', 'invertido', 'valorizado_manual'
      escenario: dict con cambios (tasa_cambio_pp, mep_cambio_pct, etc.)
      duraciones: dict {ticker: modified_duration} de Bonistas (opcional)

    Retorna dict con:
      - por_posicion: lista de {ticker, tipo, valor_actual, impacto, impacto_pct}
      - por_tipo: dict {tipo: impacto_total}
      - total: impacto total en ARS
      - total_pct: impacto total como % del patrimonio
    """
    if duraciones is None:
        duraciones = {}

    delta_tasa = escenario.get("tasa_cambio_pp", 0) / 100
    delta_mep = escenario.get("mep_cambio_pct", 0) / 100
    delta_infl = escenario.get("inflacion_cambio_pp", 0) / 100
    delta_riesgo = escenario.get("riesgo_pais_bp", 0)

    resultados = []
    por_tipo = {}
    total_valor = 0

    for p in cartera:
        valor = p.get("valorizado_manual") or p.get("invertido", 0)
        tipo = p.get("tipo", "otro")
        ticker = p.get("ticker", "?")
        total_valor += valor

        sens = _sensibilidad_por_tipo(tipo)
        duration = duraciones.get(ticker)

        if tipo in ("bono_usd", "bono_cer", "bono_fija") and duration:
            impacto_tasa = -duration * delta_tasa * valor
        else:
            impacto_tasa = sens["tasa"] * delta_tasa * valor

        impacto_mep = sens["mep"] * delta_mep * valor
        impacto_infl = sens["inflacion"] * delta_infl * valor
        impacto_riesgo = sens["riesgo"] * delta_riesgo * valor

        impacto = impacto_tasa + impacto_mep + impacto_infl + impacto_riesgo
        impacto_pct = (impacto / valor * 100) if valor else 0

        resultados.append({
            "ticker": ticker,
            "tipo": tipo,
            "valor_actual": valor,
            "impacto": round(impacto),
            "impacto_pct": round(impacto_pct, 1),
        })

        por_tipo[tipo] = por_tipo.get(tipo, 0) + impacto

    total = sum(r["impacto"] for r in resultados)
    total_pct = (total / total_valor * 100) if total_valor else 0

    return {
        "nombre": escenario.get("nombre", "?"),
        "por_posicion": resultados,
        "por_tipo": {k: round(v) for k, v in por_tipo.items()},
        "total": round(total),
        "total_pct": round(total_pct, 1),
    }


def resumen_escenarios(cartera: list, duraciones: dict = None) -> list:
    """Aplica todos los escenarios predefinidos y devuelve lista de resultados."""
    return [aplicar_escenario(cartera, e, duraciones) for e in ESCENARIOS]


if __name__ == "__main__":
    print("=== Test escenarios.py ===\n")

    cartera_ejemplo = [
        {"ticker": "AO27", "tipo": "bono_usd", "invertido": 104_440,
         "valorizado_manual": None},
        {"ticker": "_IOLPORA", "tipo": "fci", "invertido": 106_900,
         "valorizado_manual": 110_318},
        {"ticker": "_INSTITUA", "tipo": "fci", "invertido": 138_970,
         "valorizado_manual": 139_936},
        {"ticker": "_BCMMA", "tipo": "fci", "invertido": 235_180,
         "valorizado_manual": 235_829},
    ]
    duraciones = {"AO27": 1.2}

    for esc in ESCENARIOS:
        res = aplicar_escenario(cartera_ejemplo, esc, duraciones)
        signo = "+" if res["total"] >= 0 else ""
        print(f"  {esc['emoji']} {esc['nombre']:30s} -> {signo}${res['total']:>10,}"
              f"  ({signo}{res['total_pct']:.1f}%)")
