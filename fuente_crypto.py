"""
fuente_crypto.py — Precio USDT/ARS y spread vs MEP/CCL
Fuentes: CoinGecko (gratuita, sin API key) + Binance P2P
"""

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (CarteraInversor/6.0; lectura personal)",
    "Accept": "application/json",
}
TIMEOUT = 10


def get_usdt_ars_coingecko() -> float | None:
    """USDT/ARS desde CoinGecko (sin API key)."""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "tether", "vs_currencies": "ars"},
            headers=HEADERS, timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("tether", {}).get("ars")
    except Exception:
        return None


def get_usdt_ars_binance_p2p(trade_type: str = "BUY") -> float | None:
    """
    Precio mediano de USDT/ARS en Binance P2P.
    trade_type: "BUY" (compra USDT con ARS) o "SELL" (venta USDT por ARS).
    """
    try:
        payload = {
            "fiat": "ARS",
            "page": 1,
            "rows": 10,
            "tradeType": trade_type,
            "asset": "USDT",
            "payTypes": [],
        }
        r = requests.post(
            "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search",
            json=payload, headers=HEADERS, timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return None
        prices = [float(ad["adv"]["price"]) for ad in data[:5]]
        return sum(prices) / len(prices)
    except Exception:
        return None


def get_crypto_spread(mep_venta: float | None = None) -> dict:
    """
    Devuelve precios USDT/ARS y spread vs MEP.
    mep_venta: precio de venta del dólar MEP (para calcular spread).
    """
    coingecko = get_usdt_ars_coingecko()
    binance_buy = get_usdt_ars_binance_p2p("BUY")
    binance_sell = get_usdt_ars_binance_p2p("SELL")

    usdt = coingecko or binance_buy

    spread_vs_mep = None
    conviene = None
    if usdt and mep_venta and mep_venta > 0:
        spread_vs_mep = (usdt / mep_venta - 1) * 100
        if spread_vs_mep < -0.5:
            conviene = "CRIPTO"
        elif spread_vs_mep > 0.5:
            conviene = "MEP"
        else:
            conviene = "SIMILAR"

    return {
        "usdt_ars": round(usdt, 2) if usdt else None,
        "coingecko": round(coingecko, 2) if coingecko else None,
        "binance_buy": round(binance_buy, 2) if binance_buy else None,
        "binance_sell": round(binance_sell, 2) if binance_sell else None,
        "spread_vs_mep_pct": round(spread_vs_mep, 2) if spread_vs_mep is not None else None,
        "conviene": conviene,
    }


if __name__ == "__main__":
    print("=== USDT/ARS ===")
    data = get_crypto_spread(mep_venta=1477)
    for k, v in data.items():
        print(f"  {k}: {v}")
