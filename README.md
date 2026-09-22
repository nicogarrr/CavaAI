# CavaAI — Research OS de inversión personal

![CI](https://github.com/nicogarrr/CavaAI/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-All%20rights%20reserved-lightgrey)
![Stack](https://img.shields.io/badge/Next.js_16-%2B-FastAPI-blue)

**CavaAI es tu memoria de inversor a largo plazo.** No es un terminal más ni una fábrica de DCF: es donde vive por qué sigues o posees cada empresa, qué evidencias sostienen tu tesis, qué la contradice y qué ha cambiado con el tiempo.

> Esto no es asesoramiento financiero. Los datos pueden llegar con retraso o estar incompletos según el proveedor.

## Qué hace

- **Workspace por empresa** (`/research/[ticker]`): snapshot coherente, tesis versionada con auditoría, claims con evidencia a favor/en contra, memoria y chat con fuentes.
- **Tesis con abogado del diablo**: debate bull/bear automático con veredicto persistido en la tesis.
- **Valoración determinista**: DCF, SOTP, pre-revenue, bancos, aseguradoras, REITs, holdings y materias primas — con traza de cálculo y regla anti-look-ahead (sin datos futuros).
- **Señales insider**: compras de directivos desde SEC EDGAR (Form 4, gratis), con detección de cluster-buy y alerta en Telegram.
- **Alertas en Telegram**: reglas de precio/noticias/earnings + urgencia puntuada por IA; las tesis se aprueban desde el propio Telegram (Publicar / Revisar).
- **Biblioteca de conocimiento (RAG)**: sube PDFs/MDs, extrae principios, apruébalos y pregúntales con búsqueda semántica (Qdrant + embeddings locales).
- **Tesis en EPUB**: descarga cada tesis para leerla en tu e-reader/Kindle.
- **Screener real, portfolio con IBKR, calendario de earnings/dividendos, diario de decisión y fiscalidad.**

## De dónde vienen los datos (todo verificable)

| Fuente | Qué aporta | Coste |
|---|---|---|
| Yahoo Finance | Índices reales (^GSPC, ^IXIC, BTC-USD, GC=F, SI=F), fallback de quotes | Gratis |
| Finnhub | Quotes, perfiles, noticias, calendario (caché ~60 s) | Free tier |
| SEC EDGAR | Filings 10-K/10-Q y Form 4 de insiders | Gratis, sin key |
| FRED | Macro (IPC, paro, tipos) | Gratis (key gratuita) |
| Calendario NASDAQ | Earnings y dividendos | Gratis |
| OpenCode Go (+ Jev) | Solo texto de análisis y micro-decisiones; **nunca inventa cifras** | Suscripción / $0.042 por millón de tokens |

FMP está retirado (su API legacy dejó de funcionar); no hay tickers ni nombres hardcodeados: todo nombre visible viene de una API real.

## Arranque rápido (< 30 min)

**Opción A — stack completo con Docker:**

```bash
cp docker.env.example .env
# edita .env con tus claves (Finnhub, Telegram, OpenCode Go…)
docker compose up --build
```

Abre http://localhost:3000. Servicios: PostgreSQL, MongoDB (auth), Qdrant (vectores), MinIO (documentos), Redis.

**Opción C — GitHub Codespaces (sin cargar tu portátil):**

El repo incluye `.devcontainer/`: al crear un codespace se levanta la pila completa
(PostgreSQL, MongoDB, Redis, Qdrant, MinIO, backend FastAPI y frontend Next.js) y
quedas editando dentro del contenedor con Node 22 y Python 3.

1. En GitHub: **Code -> Codespaces -> Create codespace on main**.
2. Espera a que termine el arranque y abre el puerto 3000 (se reenvía solo).
3. La cuenta personal gratuita incluye 120 core-hours/mes (~60 h con la máquina
   de 2 cores) y 15 GB de almacenamiento; configura el auto-stop a 15-30 min en
   tus ajustes de Codespaces para no gastar cuota.
4. En una máquina de 2 cores puedes ahorrar RAM parando lo que no uses:
   `docker compose stop worker scheduler`.

**Opción B — desarrollo por piezas:**

```bash
# Backend
cd data-engine
python -m venv .venv && ./.venv/Scripts/activate  # Windows
pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# Frontend (otra terminal, desde la raíz)
npm install
npm run dev
```

**Variables mínimas** (ver `docker.env.example` para la lista completa):

```env
MONGODB_URI=mongodb://root:***@localhost:27017/cavaai?authSource=admin
BETTER_AUTH_SECRET=secreto_de_32_caracteres_minimo
RESEARCH_AUTH_SECRET=otro_secreto_independiente_de_32
FINNHUB_API_KEY=
OPENCODE_GO_API_KEY=
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Genera secretos con `openssl rand -base64 32`. **Nunca commitees el `.env`** (está en `.gitignore`: solo se versionan los `.example`).

## Verificación

```bash
# Frontend
./node_modules/.bin/tsc --noEmit
npm run lint
npm run build

# Backend (suite completa ~2 min)
cd data-engine && ./.venv/Scripts/python.exe -m pytest tests/ -q

# El cliente OpenAPI no debe derivar (regenerar si tocas rutas)
npm run generate:openapi
git diff --exit-code -- data-engine/openapi.json lib/research/openapi.generated.ts
```

El CI ejecuta 7 jobs: calidad frontend/backend, drift OpenAPI, migraciones Postgres, auditoría de dependencias y e2e (API + navegador).

## Arquitectura en 30 segundos

Next.js (App Router, server actions firmadas HMAC) habla con FastAPI
(`/api/*`, firma X-CavaAI-*): Postgres como canónico, Qdrant como índice
semántico reconstruible, MinIO para originales y Redis/Dramatiq para jobs.
OpenCode Go es el único LLM y Jev hace las micro-decisiones.

Autenticación doble: sesiones Better Auth en MongoDB + firma HMAC con secreto
de 32 mínimo en la research API (ventana 300 s, tenant = tu userId).

## Estructura

```
app/(root)/          páginas: research, screener, watchlist, portfolio,
                     alerts, knowledge, propicks, metodologia…
components/          UI (shadcn/Radix + Tailwind oscuro)
lib/actions/         server actions · lib/research/  cliente firmado
data-engine/
  app/api/routes/    26 routers bajo /api
  app/services/      ingesta, tesis, debate, insider, RAG, alertas…
  app/valuation/     motores + guardia point-in-time
  app/llm/           factory OpenCode Go + cliente Jev
  alembic/versions/  migraciones 0001→0020 (lineales, con downgrade)
  tests/             250+ tests herméticos · evals/  evals financieras
e2e/                 specs Playwright del flujo inversor
docs/                PRODUCT_VISION, runbooks, privacidad
```

Ver [docs/PRODUCT_VISION.md](docs/PRODUCT_VISION.md) y la propia app en
`/metodologia` (fuentes, límites y costes).

## Producción

- Frontend en Vercel; backend con autoarranque local o `render.yaml`.
- Migraciones siempre explícitas (`alembic upgrade head`); el seed solo instala taxonomía pública, nunca tu cartera.
- Puertos de BD cerrados al exterior; secretos solo en el dashboard de deploy.
- Qdrant se reconstruye desde Postgres (`RAGIndex().rebuild_tenant`).

## Licencia

Copyright 2025 Nicolás Iglesias García. Todos los derechos reservados.
