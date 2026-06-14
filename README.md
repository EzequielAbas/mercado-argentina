# 🇦🇷 Mercado Argentino — API de datos públicos

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/EzequielAbas/mercado-argentina)

API REST gratuita con datos de mercado argentino: bonos, FX implícito, dólares,
riesgo país, FCIs, noticias y análisis técnico. Consume fuentes públicas:
**Bonistas.com**, **Rava**, **ArgentinaDatos**, **CAFCI** y feeds RSS.

> ⚠️ Este repo **no contiene datos personales**: ni cartera, ni sueldos, ni
> credenciales. Eso vive en un repo privado aparte que consume esta API.

---

## Endpoints

| Endpoint | Descripción | Cache |
|---|---|---|
| `GET /salud` | Health check | — |
| `GET /macro` | MEP, CCL, oficial, blue, riesgo país, Merval | 5 min |
| `GET /dolares` | Todas las cotizaciones del dólar | 5 min |
| `GET /riesgo-pais` | Riesgo país actual | 5 min |
| `GET /fx` | FX implícito por bono (Bonistas) | 5 min |
| `GET /bonos?familia=cer` | Bonos por familia: `soberanos_usd`, `cer`, `lecap`, `on` | 5 min |
| `GET /fci/{tipo}` | FCIs: `mercadoDinero`, `rentaFija`, `rentaVariable`, `rentaMixta` | 1 hr |
| `GET /noticias` | RSS filtrado por keywords de inversión | 10 min |
| `GET /tecnico/{ticker}` | RSI, EMAs, señal técnica (vía yfinance) | — |
| `GET /screener` | Score técnico Merval + CEDEARs | 30 min |
| `GET /feriados/{anio}` | Feriados del año | 24 hr |

---

## Uso local

```bash
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

Swagger interactivo: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Uso como librería

```python
import fuente_bonistas, fuente_argentinadatos, fuente_rava

df_bonos = fuente_bonistas.get_bonds()
macro = fuente_argentinadatos.get_macro()
home = fuente_rava.get_home()
```

---

## Deploy en Render (gratis)

1. Forkeá o conectá este repo en [render.com](https://render.com)
2. Creá un **Web Service** → rama `main`
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn api:app --host 0.0.0.0 --port $PORT`
5. Plan: **Free**

O usá el botón "Deploy to Render" de arriba.

---

## Módulos

| Módulo | Fuente | Qué hace |
|---|---|---|
| `fuente_bonistas` | Bonistas.com | Bonos, FX implícito, estado de mercado |
| `fuente_rava` | Rava Bursátil | Merval, riesgo país, cotizaciones |
| `fuente_argentinadatos` | ArgentinaDatos API | Dólares, macro, FCIs, feriados |
| `fuente_cafci` | CAFCI | Cuotapartes de FCIs |
| `noticias` | Feeds RSS | Noticias financieras filtradas |
| `analisis_tecnico` | yfinance | RSI, EMAs, señales técnicas |
| `indicadores_avanzados` | yfinance | Indicadores complementarios |
| `screener` | yfinance | Screener técnico multi-papel |

---

## Stack

Python 3.11+ · FastAPI · pandas · BeautifulSoup4 · yfinance · feedparser

## Licencia

MIT — No constituye asesoramiento financiero.
