# Arquitectura de CavaAI

> Estado: consolidación de backend completada (agosto 2026). La API legacy
> (`data-engine/routers/`) fue retirada del servicio; el único API del data
> engine es el research API bajo el prefijo `/api`.

## 1. Visión general

```
┌────────────────────────── Next.js (frontend) ──────────────────────────┐
│  App Router · Server Actions · mejor-auth con sesiones en MongoDB      │
│                                                                         │
│  lib/research/client.ts  ── researchRequest(path) ──►  FMP_BACKEND_URL  │
│       │  headers firmados:                                              │
│       │  X-CavaAI-User / X-CavaAI-Tenant / X-CavaAI-Timestamp /        │
│       │  X-CavaAI-Signature (HMAC-SHA256 con RESEARCH_AUTH_SECRET,      │
│       │  tenant = user.id, TTL 300s)                                    │
└───────┼─────────────────────────────────────────────────────────────────┘
        ▼
┌────────────────────────── FastAPI data-engine ─────────────────────────┐
│  main.py · lifespan (seed, model aliases, scheduler si WORKERS_ENABLED) │
│                                                                         │
│  /api/*              research API privado  → auth HMAC → tenant scope   │
│  /api/health         público (sin firma): BD + scheduler + versión      │
│  /health /live /ready liveness/readiness clásicos                       │
│                                                                         │
│  Postgres (DATABASE_URL) — migraciones Alembic (alembic/versions/)      │
│  Worker scheduler (APScheduler → Dramatiq/Redis)                        │
└─────────────────────────────────────────────────────────────────────────┘
```

## 2. Frontend → investigación (identidad y tenant)

- **Sesión**: `mejor-auth` (`lib/better-auth/auth.ts`) con adaptador MongoDB
  (`@/database/mongoose`). La sesión vive en MongoDB, no en la BD del engine.
- **Puente al backend**: `lib/research/client.ts` (`researchRequest`) firma la
  identidad del usuario autenticado con `RESEARCH_AUTH_SECRET`
  (HMAC-SHA256 sobre `{tenant}:{user}:{timestamp}`) y la envía en los headers
  `X-CavaAI-*`. El navegador nunca construye estos headers: solo el servidor
  Next.js los genera (server actions).
- **Tenant**: el tenant del backend ES el `user.id` de mejor-auth
  (`lib/auth/research-identity.ts`, `tenantId = user.id`). FastAPI lo valida en
  `app/core/auth.py` (`get_research_principal`) y lo usa para aislar datos por
  tenant en `app/core/database.py` (queries e inserts con scope de tenant).

## 3. FastAPI data-engine

- **Bootstrap** (`main.py`): lifespan arranca seed de company master (no en
  producción), configura aliases de modelos LLM, valida configuración y — si
  `WORKERS_ENABLED=true` — arranca el scheduler de workers.
- **Routers**:
  - Todo el research API vive en `app/api/router.py`, montado en `/api` con
    auth obligatoria (`Depends(get_research_principal)`). Incluye companies,
    portfolio, watchlist, thesis, news, risk, chat, knowledge, screeners, etc.
  - `/api/health` se monta en `main.py` **fuera** del router autenticado y es
    público: `{status, database (SELECT 1), scheduler {enabled, running, jobs,
    last_run_at}, version: "main-<sha corto>"}`.
  - `/health`, `/health/live`, `/health/ready` públicos (liveness/readiness
    clásicos con checks de BD/Redis/Qdrant/MinIO).
- **BD**: Postgres (`postgresql+psycopg://…`) en dev/producción; SQLite en
  tests (`cavaai_test.db`, hermético, `APP_ENV=test`). Migraciones con Alembic
  (`alembic upgrade head`; última: `0019_watchlist`).
- **Rate limiting**: `RateLimitMiddleware` global (120 req/min; 20/min para
  endpoints caros).

## 4. Fuentes de datos de mercado

| Fuente | Uso | Dónde |
|---|---|---|
| **Finnhub** | Quotes de acciones vía frontend (`lib/actions/finnhub.actions.ts`, `FINNHUB_API_KEY`) | Next.js |
| **Yahoo Finance** | Índices (S&P 500, Nasdaq, BTC, oro, plata) vía `GET /api/market/indices` (`app/api/routes/market.py`), sin key, con cache en memoria de 60 s | data-engine |
| **FMP** | Antigua fuente de fundamentales/market data en `modules/fmp` — **en proceso de retirada**; sus routers legacy se eliminaron | legado |

## 5. Trabajos programados (workers)

- **Fuente de verdad — backend**: `app/workers/scheduler.py` construye un
  scheduler APScheduler (`build_scheduler`) con jobs que encolan actores
  Dramatiq (`app/workers/dramatiq_app.py`, broker Redis) para cada tenant:
  refresh de market/noticias/RSS/SEC/IR, consolidación de memoria, revisión de
  tesis, investigación diaria y escaneo de contradicciones. Se arranca en el
  lifespan de FastAPI solo si `WORKERS_ENABLED=true` (desactivado en tests).
- **Secundario — frontend**: `lib/inngest/*` (Inngest) gestiona **emails**
  (bienvenida, resumen diario de noticias). División documentada: los datos y
  el research corren en el scheduler del backend; Inngest queda limitado a
  comunicaciones por email.
- **Canal de alertas**: Telegram es el canal primario de notificaciones
  (`TELEGRAM_ENABLED`, `notification_service`), usado por los flujos del
  backend.

## 6. Ejecución local

```bash
# Backend (data-engine/)
cd data-engine
python -m venv .venv && ./.venv/Scripts/pip install -r requirements.txt
# .env con DATABASE_URL (Postgres local), RESEARCH_AUTH_SECRET (≥32 chars), etc.
./.venv/Scripts/alembic upgrade head
./.venv/Scripts/python -m uvicorn main:app --reload --port 8000

# Frontend (raíz)
npm install
npm run dev            # http://localhost:3000 (FMP_BACKEND_URL=http://localhost:8000)

# Tests del backend
./.venv/Scripts/python -m pytest tests/ -q
```

## 7. Despliegue — variables de entorno requeridas

| Variable | Obligatoria | Notas |
|---|---|---|
| `DATABASE_URL` | sí | Postgres; migraciones vía Alembic antes de arrancar |
| `RESEARCH_AUTH_SECRET` | sí (producción) | ≥32 chars; compartida con el frontend; sin ella el API autenticado da 503/401 |
| `WORKERS_ENABLED` | no (default true) | `false` desactiva el scheduler (tests, workers aparte) |
| `FINNHUB_API_KEY` | según features | quotes del frontend |
| `OPENCODE_GO_API_KEY` / `OPENCODE_GO_MODEL` | sí (LLM) | provider LLM único (`llm_provider=opencode-go`) |
| `MINIO_*` | sí (producción) | almacenamiento de documentos originales |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | según features | canal de alertas primario |
| `REDIS_URL`, `QDRANT_URL` | según features | broker Dramatiq y vectores |
| `APP_ENV` | sí | `test` / `local` / `production` (valida secretos en prod) |