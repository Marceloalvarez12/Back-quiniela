# Integración Back-quiniela ↔ Front-quiniela

## 1) Arquitectura

```
┌──────────────────────────┐    HTTP/JSON (CORS *)    ┌─────────────────────────────┐
│  Front-quiniela (Next 16)│  ─────────────────────►  │  Back-quiniela (FastAPI)    │
│  NEXT_PUBLIC_API_URL     │  ◄─────────────────────  │  http://localhost:8000     │
└──────────────────────────┘    Tipado Pydantic v2     └─────────────────────────────┘
```

Repo backend: `C:\Users\MARCELO ALVAREZ\Back-quiniela` (rama `main`).
Repo frontend: `C:\Users\MARCELO ALVAREZ\Front-quiniela` (rama `main`).

## 2) Endpoints consumidos

| Frontend (v0)              | Backend (Back-quiniela)             | Notas                                                                                |
|----------------------------|-------------------------------------|--------------------------------------------------------------------------------------|
| `GET /api/estadisticas`    | `GET /api/estadisticas`             | Adapter en el FE: array `[{numero,frecuencia}]` → `Record<string, number>`.          |
| `GET /api/sueños?texto=…`  | `GET /api/sueños` (con ñ, **alias**) | Adapter en el FE: `detalles` → `{numero, significado}`. El backend expone ambos.    |
| (no en uso todavía)        | `GET /api/sorteos`                  | Resultados en vivo del día.                                                         |
| (no en uso todavía)        | `GET /api/health`                   | Healthcheck.                                                                        |

> **Por qué DOS rutas para sueños**: el componente v0 hace `fetch('/api/sueños?texto=...')` (con ñ).
> El backend expone ambos para que cualquier frontend funcione, incluso si alguien cambia
> el código por la versión ASCII.

## 3) Cómo correrlo en local (2 terminales)

### Terminal 1 — Backend
```bash
cd C:\Users\MARCELO ALVAREZ\Back-quiniela
.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
# Swagger: http://localhost:8000/docs
```

### Terminal 2 — Frontend
```bash
cd C:\Users\MARCELO ALVAREZ\Front-quiniela
pnpm install
echo NEXT_PUBLIC_API_URL=http://localhost:8000 > .env.local
pnpm dev
# App: http://localhost:3000
```

El frontend lee `process.env.NEXT_PUBLIC_API_URL` desde `lib/api.ts`. Si no está
definida, usa `http://localhost:8000`.

## 4) Cómo correrlo todo con UN solo comando (desde el backend)

```bash
cd C:\Users\MARCELO ALVAREZ\Back-quiniela
node scripts/orquestar_local.js
```

Ese script (Node, sin dependencias extra) arranca los 2 procesos lado a lado y
los termina juntos con Ctrl+C. Requiere Node 18+.

## 5) Despliegue (producción)

1. **Backend**: subilo a Render/Railway/Fly. Como es FastAPI estándar, el
   `Procfile` o `render.yaml` usual es:
   ```
   web: uvicorn app:app --host 0.0.0.0 --port $PORT
   ```
   No requiere variables de entorno. CORS ya está abierto.

2. **Frontend** (Vercel): en **Project Settings → Environment Variables**
   agregar `NEXT_PUBLIC_API_URL` con la URL del backend desplegado. Vercel
   redeplega automáticamente.

3. El backend **NO** expone CORS restringido → tu IP nunca se filtra. Si más
   adelante necesitás cerrar, cambiá `allow_origins` en `app.py`.

## 6) Cambios concretos que hice en cada repo

### `Back-quiniela/app.py`
- Agregué alias `GET /api/sueños` (con ñ) → mismo handler que `/api/suenos`.

### `Front-quiniela/`
- `NEXT_PUBLIC_API_URL` lee desde `.env.local` (default `http://localhost:8000`).
- `lib/api.ts` centraliza el cliente HTTP + tipos + adaptadores.
- `components/quiniela-dashboard.tsx`: usa `BACKEND` desde `lib/api.ts`,
  aplica los adaptadores, y muestra números "A la cabeza" con etiqueta clara.
- `.env.example` documentado.
- `README.md` actualizado.

## 7) Verificación E2E

Levantado el backend, podés confirmar la integración con:

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/estadisticas
curl --get --data-urlencode "texto=soñé con un gato negro" http://localhost:8000/api/sueños
```

Y desde el frontend, abrir `http://localhost:3000`, ir a la pestaña
**"Panel de la Caja Popular"** y **"El Oráculo"** y verificar que las cards
dejen de mostrar el `fallbackStats` (los números leyendas `07/22/41/13/88`)
y muestren los reales del CSV local (`16/47/96/01/41` y `32/...` etc.).
