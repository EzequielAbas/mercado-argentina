"""
clustering_activos.py — Clustering de activos por riesgo/retorno con K-means

Clasifica bonos y activos en grupos usando machine learning no supervisado.
Genera un scatter plot SVG de TIR vs Duration coloreado por cluster.

Dependencias: pandas, numpy, scikit-learn
"""

import pandas as pd
import numpy as np

try:
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    _SK = True
except ImportError:
    _SK = False


COLORES_CLUSTER = ["#00d4aa", "#4fc3f7", "#ffc107", "#ff6b6b", "#b388ff", "#ff9800"]

ETIQUETAS_DEFAULT = {
    0: "Conservador / Corto plazo",
    1: "Equilibrado",
    2: "Alto rendimiento / Largo plazo",
    3: "Agresivo",
    4: "Especulativo",
}


def preparar_features(df: pd.DataFrame) -> pd.DataFrame | None:
    """
    Prepara features para clustering desde un DataFrame de Bonistas.
    Requiere columnas: ticker, tir, modified_duration, days_to_finish.

    Retorna DataFrame con features numericas listas para KMeans.
    """
    cols_req = ["ticker", "tir", "modified_duration"]
    for c in cols_req:
        if c not in df.columns:
            return None

    feat = df[["ticker"]].copy()
    feat["tir"] = pd.to_numeric(df["tir"], errors="coerce")
    feat["duration"] = pd.to_numeric(df["modified_duration"], errors="coerce")
    if "days_to_finish" in df.columns:
        feat["dias_vto"] = pd.to_numeric(df["days_to_finish"], errors="coerce")
    else:
        feat["dias_vto"] = np.nan

    feat = feat.dropna(subset=["tir", "duration"])
    feat = feat[(feat["tir"] > 0) & (feat["tir"] < 2) & (feat["duration"] > 0)]

    if len(feat) < 6:
        return None
    return feat.reset_index(drop=True)


def _metodo_codo(X: np.ndarray, max_k: int = 6) -> int:
    """Encuentra el K optimo usando el metodo del codo."""
    if len(X) < 6:
        return 2
    max_k = min(max_k, len(X) - 1)
    inercias = []
    for k in range(2, max_k + 1):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        km.fit(X)
        inercias.append(km.inertia_)

    if len(inercias) < 2:
        return 2

    # Buscar el "codo": donde la mejora marginal cae mas
    mejoras = [inercias[i] - inercias[i+1] for i in range(len(inercias)-1)]
    if not mejoras:
        return 3
    mejor_k = 2
    max_caida = 0
    for i in range(len(mejoras) - 1):
        caida = mejoras[i] - mejoras[i+1]
        if caida > max_caida:
            max_caida = caida
            mejor_k = i + 3
    return min(mejor_k, max_k)


def clusterizar(feat: pd.DataFrame, n_clusters: int = None) -> tuple:
    """
    Ejecuta K-means sobre las features.

    Retorna:
      (df_con_cluster, info_dict)
    donde info_dict tiene: n_clusters, centroids, etiquetas.
    """
    if not _SK:
        return feat, {"error": "scikit-learn no instalado"}

    X_cols = ["tir", "duration"]
    X_raw = feat[X_cols].values

    scaler = StandardScaler()
    X = scaler.fit_transform(X_raw)

    if n_clusters is None:
        n_clusters = _metodo_codo(X)

    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    feat = feat.copy()
    feat["cluster"] = km.fit_predict(X)

    # Centroides en escala original
    centroids_scaled = km.cluster_centers_
    centroids_orig = scaler.inverse_transform(centroids_scaled)

    # Etiquetar clusters por TIR promedio (menor TIR = mas conservador)
    orden = np.argsort(centroids_orig[:, 0])
    etiquetas = {}
    for rank, idx in enumerate(orden):
        if rank == 0:
            etiquetas[int(idx)] = "Conservador / Corto plazo"
        elif rank == n_clusters - 1:
            etiquetas[int(idx)] = "Alto rendimiento / Largo plazo"
        else:
            etiquetas[int(idx)] = f"Equilibrado ({rank})"

    info = {
        "n_clusters": n_clusters,
        "centroids": {int(i): {"tir": round(c[0], 4), "duration": round(c[1], 2)}
                      for i, c in enumerate(centroids_orig)},
        "etiquetas": etiquetas,
    }
    return feat, info


def generar_scatter_svg(feat: pd.DataFrame, info: dict,
                        tickers_propios: list = None,
                        ancho: int = 500, alto: int = 300) -> str:
    """
    Genera un SVG scatter plot: X=duration, Y=TIR, color por cluster.
    Destaca los tickers que el usuario tiene en cartera.
    """
    if feat.empty or "cluster" not in feat.columns:
        return ""

    margin = {"t": 20, "r": 20, "b": 40, "l": 50}
    plot_w = ancho - margin["l"] - margin["r"]
    plot_h = alto - margin["t"] - margin["b"]

    dur_min = feat["duration"].min() * 0.9
    dur_max = feat["duration"].max() * 1.1
    tir_min = feat["tir"].min() * 0.9
    tir_max = feat["tir"].max() * 1.1
    dur_range = dur_max - dur_min if dur_max != dur_min else 1
    tir_range = tir_max - tir_min if tir_max != tir_min else 1

    propios = set(t.upper() for t in (tickers_propios or []))
    dots = []
    labels_propios = []

    for _, r in feat.iterrows():
        cx = margin["l"] + (r["duration"] - dur_min) / dur_range * plot_w
        cy = margin["t"] + plot_h - (r["tir"] - tir_min) / tir_range * plot_h
        cluster = int(r.get("cluster", 0))
        color = COLORES_CLUSTER[cluster % len(COLORES_CLUSTER)]
        ticker = r.get("ticker", "")
        es_propio = ticker.upper() in propios

        radius = 6 if es_propio else 4
        stroke = 'stroke="#fff" stroke-width="2"' if es_propio else ""
        dots.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius}" '
                    f'fill="{color}" opacity="0.8" {stroke}/>')
        if es_propio:
            labels_propios.append(
                f'<text x="{cx:.1f}" y="{cy - 10:.1f}" text-anchor="middle" '
                f'font-size="9" fill="#fff" font-weight="bold">{ticker}</text>')

    # Ejes
    axes = []
    # Eje X (duration)
    axes.append(f'<line x1="{margin["l"]}" y1="{margin["t"] + plot_h}" '
                f'x2="{margin["l"] + plot_w}" y2="{margin["t"] + plot_h}" '
                f'stroke="#566a7f" stroke-width="1"/>')
    axes.append(f'<text x="{margin["l"] + plot_w // 2}" y="{alto - 5}" '
                f'text-anchor="middle" font-size="10" fill="#8899aa">'
                f'Duration (mod.)</text>')
    # Eje Y (TIR)
    axes.append(f'<line x1="{margin["l"]}" y1="{margin["t"]}" '
                f'x2="{margin["l"]}" y2="{margin["t"] + plot_h}" '
                f'stroke="#566a7f" stroke-width="1"/>')
    axes.append(f'<text x="12" y="{margin["t"] + plot_h // 2}" '
                f'text-anchor="middle" font-size="10" fill="#8899aa" '
                f'transform="rotate(-90,12,{margin["t"] + plot_h // 2})">'
                f'TIR anual</text>')

    # Ticks X
    for i in range(5):
        x = margin["l"] + i / 4 * plot_w
        val = dur_min + i / 4 * dur_range
        axes.append(f'<text x="{x:.0f}" y="{margin["t"] + plot_h + 14}" '
                    f'text-anchor="middle" font-size="8" fill="#566a7f">'
                    f'{val:.1f}</text>')
    # Ticks Y
    for i in range(5):
        y = margin["t"] + plot_h - i / 4 * plot_h
        val = tir_min + i / 4 * tir_range
        axes.append(f'<text x="{margin["l"] - 4}" y="{y + 3:.0f}" '
                    f'text-anchor="end" font-size="8" fill="#566a7f">'
                    f'{val:.0%}</text>')

    # Leyenda
    etiquetas = info.get("etiquetas", {})
    legend = []
    for cl, label in sorted(etiquetas.items()):
        color = COLORES_CLUSTER[cl % len(COLORES_CLUSTER)]
        lx = margin["l"] + 10
        ly = margin["t"] + 12 + cl * 14
        legend.append(f'<rect x="{lx}" y="{ly - 6}" width="8" height="8" '
                      f'rx="2" fill="{color}"/>')
        legend.append(f'<text x="{lx + 12}" y="{ly + 2}" font-size="8" '
                      f'fill="#8899aa">{label}</text>')

    content = "\n".join(axes + dots + labels_propios + legend)
    return (f'<svg viewBox="0 0 {ancho} {alto}" '
            f'xmlns="http://www.w3.org/2000/svg" '
            f'style="max-width:{ancho}px;width:100%">\n{content}\n</svg>')


if __name__ == "__main__":
    print("=== Test clustering_activos.py ===\n")

    if not _SK:
        print("scikit-learn no instalado. Instalar con: pip install scikit-learn")
        raise SystemExit(0)

    # Datos sinteticos simulando bonos
    np.random.seed(42)
    tickers = [f"BONO{i:02d}" for i in range(20)]
    data = pd.DataFrame({
        "ticker": tickers,
        "tir": np.concatenate([
            np.random.uniform(0.05, 0.12, 7),
            np.random.uniform(0.12, 0.25, 7),
            np.random.uniform(0.25, 0.45, 6),
        ]),
        "modified_duration": np.concatenate([
            np.random.uniform(0.3, 1.5, 7),
            np.random.uniform(1.5, 4, 7),
            np.random.uniform(4, 10, 6),
        ]),
        "days_to_finish": np.concatenate([
            np.random.uniform(30, 365, 7),
            np.random.uniform(365, 1500, 7),
            np.random.uniform(1500, 4000, 6),
        ]),
    })

    feat = preparar_features(data)
    if feat is None:
        print("No hay suficientes datos")
        raise SystemExit(0)

    feat, info = clusterizar(feat)
    print(f"Clusters encontrados: {info['n_clusters']}")
    for cl, label in info["etiquetas"].items():
        c = info["centroids"][cl]
        n = len(feat[feat["cluster"] == cl])
        print(f"  [{cl}] {label}: TIR={c['tir']:.1%}, Dur={c['duration']:.1f} ({n} bonos)")

    svg = generar_scatter_svg(feat, info, tickers_propios=["BONO03", "BONO15"])
    print(f"\nSVG scatter generado: {len(svg)} chars")
