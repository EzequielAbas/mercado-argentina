"""
analisis_cartera.py — Analisis de cartera: retornos mensuales y correlacion

Funciones para:
  - Calcular retornos mes a mes desde historial_patrimonio.json
  - Matriz de correlacion entre categorias de activos
  - Generar SVG heatmap inline para el reporte HTML

Dependencias: pandas, numpy (ya instaladas)
"""

import pandas as pd
import numpy as np


def calcular_retornos_mensuales(historial: list) -> pd.DataFrame | None:
    """
    Recibe la lista de historial_patrimonio.json.
    Agrupa por mes y calcula retorno porcentual mes a mes.

    Retorna DataFrame con columnas:
      mes, inicio, fin, cambio, cambio_pct
    """
    if not historial or len(historial) < 2:
        return None

    df = pd.DataFrame(historial)
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha"]).sort_values("fecha")
    df["mes"] = df["fecha"].dt.to_period("M")

    mensual = df.groupby("mes").agg(
        inicio=("patrimonio", "first"),
        fin=("patrimonio", "last"),
        dias=("patrimonio", "count"),
    ).reset_index()
    mensual["mes_str"] = mensual["mes"].astype(str)
    mensual["cambio"] = mensual["fin"] - mensual["inicio"]
    mensual["cambio_pct"] = (mensual["cambio"] / mensual["inicio"] * 100).round(2)
    return mensual


def matriz_correlacion(series_dict: dict) -> pd.DataFrame | None:
    """
    Recibe dict {nombre_categoria: pd.Series de valores diarios}.
    Calcula correlacion entre los retornos diarios porcentuales.

    Retorna DataFrame cuadrado con correlaciones (-1 a +1).
    """
    if not series_dict or len(series_dict) < 2:
        return None

    df = pd.DataFrame(series_dict)
    retornos = df.pct_change().dropna()
    if len(retornos) < 5:
        return None
    return retornos.corr().round(3)


def generar_heatmap_svg(corr: pd.DataFrame, ancho: int = 400) -> str:
    """
    Genera un SVG inline con un heatmap de correlacion.
    Colores: rojo (-1) -> blanco (0) -> verde (+1).
    Compatible con el dark theme del reporte.
    """
    if corr is None or corr.empty:
        return ""

    labels = list(corr.columns)
    n = len(labels)
    cell = ancho // (n + 1)
    h_total = cell * (n + 1) + 10
    w_total = cell * (n + 1) + 10
    offset_x = cell + 5
    offset_y = cell + 5

    def _color(val):
        if pd.isna(val):
            return "#1a2736"
        v = max(-1, min(1, val))
        if v >= 0:
            r = int(255 * (1 - v))
            g = int(180 + 75 * v)
            b = int(255 * (1 - v))
            return f"rgb({r},{g},{b})"
        else:
            r = int(255 + 0 * v)
            g = int(255 * (1 + v))
            b = int(255 * (1 + v))
            return f"rgb({r},{g},{b})"

    rects = []
    texts = []
    for i, row_label in enumerate(labels):
        # Label fila (izquierda)
        y_center = offset_y + i * cell + cell // 2
        texts.append(f'<text x="{offset_x - 4}" y="{y_center + 3}" '
                     f'text-anchor="end" font-size="10" fill="#8899aa">'
                     f'{row_label[:8]}</text>')
        # Label columna (arriba)
        x_center = offset_x + i * cell + cell // 2
        texts.append(f'<text x="{x_center}" y="{offset_y - 6}" '
                     f'text-anchor="middle" font-size="10" fill="#8899aa">'
                     f'{row_label[:8]}</text>')
        for j, col_label in enumerate(labels):
            val = corr.iloc[i, j]
            color = _color(val)
            x = offset_x + j * cell
            y = offset_y + i * cell
            rects.append(f'<rect x="{x}" y="{y}" width="{cell-2}" height="{cell-2}" '
                         f'rx="3" fill="{color}" opacity="0.85"/>')
            val_str = f"{val:.2f}" if pd.notna(val) else ""
            txt_color = "#000" if abs(val) < 0.5 else "#fff"
            texts.append(f'<text x="{x + cell//2 - 1}" y="{y + cell//2 + 4}" '
                         f'text-anchor="middle" font-size="10" fill="{txt_color}">'
                         f'{val_str}</text>')

    svg_content = "\n".join(rects + texts)
    return (f'<svg viewBox="0 0 {w_total} {h_total}" '
            f'xmlns="http://www.w3.org/2000/svg" '
            f'style="max-width:{w_total}px;width:100%">\n{svg_content}\n</svg>')


if __name__ == "__main__":
    import json
    from pathlib import Path

    print("=== Test analisis_cartera.py ===\n")

    # Test retornos mensuales con datos de ejemplo
    historial_path = Path(__file__).parent.parent / "cartera-privada" / "historial_patrimonio.json"
    if historial_path.exists():
        historial = json.loads(historial_path.read_text(encoding="utf-8"))
        df = calcular_retornos_mensuales(historial)
        if df is not None:
            print("Retornos mensuales:")
            for _, r in df.iterrows():
                signo = "+" if r["cambio"] >= 0 else ""
                print(f"  {r['mes_str']}:  ${r['inicio']:,.0f} -> ${r['fin']:,.0f}"
                      f"  ({signo}{r['cambio_pct']:.1f}%)")
        else:
            print("Pocos datos para retornos mensuales")
    else:
        print(f"No se encontro historial en {historial_path}")

    # Test correlacion con datos sinteticos
    print("\nTest correlacion (datos sinteticos):")
    np.random.seed(42)
    n = 30
    base = np.cumsum(np.random.randn(n) * 0.02)
    series = {
        "USD": pd.Series(100 + base * 10 + np.random.randn(n) * 0.5),
        "CER": pd.Series(100 + base * 5 + np.random.randn(n) * 1),
        "TasaFija": pd.Series(100 + np.random.randn(n).cumsum() * 0.3),
        "MM": pd.Series(100 + np.arange(n) * 0.1 + np.random.randn(n) * 0.05),
    }
    corr = matriz_correlacion(series)
    if corr is not None:
        print(corr.to_string())
        svg = generar_heatmap_svg(corr)
        print(f"\nSVG generado: {len(svg)} chars")
