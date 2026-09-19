# Back-quiniela — Quiniela de Tucumán Inteligente: Mística & Datos

API REST en FastAPI para la aplicación Full-Stack **"Quiniela de Tucumán
Inteligente: Mística & Datos"**. Pensada para ser consumida por un frontend
React/Next.js (v0 / Vercel).

## Stack

- **FastAPI** + **Uvicorn** (servidor ASGI)
- **Pandas** + **NumPy** para cálculos estadísticos
- **Requests** + **BeautifulSoup4** para scraping best-effort
- **Pydantic v2** para tipado y validación
- **hashlib (stdlib)** para el Oráculo de los Sueños determinístico
- **logging (stdlib)** para observabilidad

## Endpoints

| Método | Ruta               | Qué devuelve                                              |
|--------|--------------------|-----------------------------------------------------------|
| GET    | `/`                | Mapa de la API.                                           |
| GET    | `/api/health`      | Healthcheck + fecha del servidor.                         |
| GET    | `/api/sorteos`     | Resultados del día (Matutina / Eléctrica / Vespertina / Nocturna). |
| GET    | `/api/estadisticas`| Top 5 calientes + Top 5 demorados + turnos del día.       |
| GET    | `/api/suenos`      | Números sugeridos a partir de un texto de sueño.          |
| GET    | `/docs`            | Swagger UI (FastAPI).                                     |
| GET    | `/openapi.json`    | Esquema OpenAPI.                                          |

> **La API nunca devuelve 500**: si el scraping falla, el CSV no tiene datos
> y el hash se rompe, devolvemos siempre un JSON válido con `advertencia`
> describiendo el modo degradado.

## Estructura

```
Back-quiniela/
├─ app.py              # FastAPI + endpoints + CORS + lifespan
├─ modelos.py          # Esquemas Pydantic
├─ data_loader.py      # Carga/generación del historial (CSV o simulado)
├─ scraper.py          # Scraper + fallbacks (sitio → CSV → determinístico)
├─ estadisticas.py     # Cálculos con Pandas/NumPy
├─ suenos.py           # Diccionario folclórico + hash SHA-256(sueño+fecha)
├─ data/
│   └─ historico_base.csv   # 600 registros de fallback (se crea al primer arranque)
├─ requirements.txt
└─ README.md
```

## Instalación

Requirimientos: **Python 3.10+** (probado con 3.11).

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

## Ejecución

```bash
# Modo desarrollo (con autoreload):
uvicorn app:app --host 0.0.0.0 --port 8000 --reload

# Modo producción:
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4

# Equivalente en Python plano:
python app.py
```

La API queda en `http://localhost:8000`. Swagger en `http://localhost:8000/docs`.

## CORS

Configurado con `allow_origins=["*"]` para que el frontend v0/Vercel pueda
consumir sin restricciones.

## Notas sobre el scraping

**Hoy (sep 2026)** verifiqué lo siguiente:

1. `https://cajapopular.gov.ar` redirige (301) a `https://www.cajapopular.gov.ar/`,
   un sitio WordPress/Divi que **no expone los resultados del día en HTML**.
2. Los resultados viven en una **SPA React** separada:
   `https://resultadosquiniela.cajapopular.gov.ar/`. La app carga datos vía
   `resultadosquiniela.cajapopular.gov.ar/api/...` (rutas no documentadas,
   detrás del bundle JS minificado).

Por eso el scraper está estructurado como **try/except estricto** con estos
niveles de fallback:

1. `requests + BeautifulSoup` a las URLs conocidas (intenta capturar los
   números si alguna vez aparecen en HTML estático).
2. Lectura del último registro de cada turno del día desde
   `data/historico_base.csv`.
3. Generación determinística sembrada con la fecha (`mock_determinista`).

Si querés un scraping **real** que renderice la SPA, instalá Playwright
(ver comentario en `scraper.py`):

```bash
pip install playwright
playwright install chromium
```

Y reemplazá `_fetch_html` por las 4 líneas de `sync_playwright`.

## Diccionario de los sueños

`suenos.py` contiene la tabla clásica de los sueños con **90 entradas**
(del 00 al 99, con sinonimias y formas declinadas). Si el texto del
usuario no tiene coincidencias, se generan 2 números vía
`SHA-256(texto | fecha)` → estables durante el día, diferentes al día
siguiente.

## Logs

Los logs se imprimen en consola con `logging` estándar:

```
2026-09-19 16:54:01 | INFO    | quiniela.scraper | Scraper: GET https://resultadosquiniela.cajapopular.gov.ar/
2026-09-19 16:54:07 | WARNING | quiniela.scraper | Scraper: fallo HTTP en ... → ConnectionError
2026-09-19 16:54:07 | INFO    | quiniela.suenos  | Sueño recibido (fecha=2026-09-19, len=24): 'soñé con un gato negro'
2026-09-19 16:54:07 | INFO    | quiniela.suenos  | Sueño procesado: numeros=['05']
```

Niveles: `INFO` (consulta normal), `WARNING` (fallback), `ERROR` (mock
determinista), `EXCEPTION` (con traceback).
