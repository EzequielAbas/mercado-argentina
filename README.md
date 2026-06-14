# Mercado Argentino — API de datos públicos

Datos de mercado argentino (bonos, FX implícito, dólares, riesgo país, noticias,
análisis técnico, screener) desde fuentes públicas: **Bonistas.com**, **Rava**,
**ArgentinaDatos** y feeds RSS.

> ⚠️ Este repo **no contiene datos personales**: ni cartera, ni sueldos, ni
> credenciales. Eso vive en un repo privado aparte que consume esta API.

## Uso como librería
```python
import fuente_bonistas, fuente_argentinadatos, fuente_rava
df = fuente_bonistas.get_bonds()
macro = fuente_argentinadatos.get_macro()
```

## Uso como API REST
```bash
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
# Swagger: http://127.0.0.1:8000/docs
```

| Endpoint | Qué devuelve |
|---|---|
| `/macro` | MEP, CCL, oficial, blue, riesgo país, Merval |
| `/dolares` | Todas las cotizaciones (ArgentinaDatos) |
| `/fx` | FX implícito por bono (Bonistas) |
| `/bonos?familia=cer` | Bonos por familia (soberanos USD / CER / LECAP / ON) |
| `/fci/mercadoDinero` | Cuotapartes de FCIs |
| `/noticias` | RSS filtrado por keywords de inversión |
| `/tecnico/XLP` | RSI, EMAs, señal (vía yfinance) |
| `/screener` | Score técnico Merval + CEDEARs (lento, cacheado) |

## Deploy gratis
Render / Railway / Fly.io: `uvicorn api:app --host 0.0.0.0 --port $PORT`

## Módulos
`fuente_bonistas` · `fuente_rava` · `fuente_argentinadatos` · `fuente_cafci` ·
`noticias` · `analisis_tecnico` · `indicadores_avanzados` · `screener`

Licencia MIT. No constituye asesoramiento financiero.
