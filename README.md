# CavaAI

CavaAI is a private Personal Investment Research OS for long-term investors. It combines company workspaces, thesis history, traceable evidence, document memory, portfolio context, news impact analysis, and valuation tools.

The core product is not a DCF factory. The core product is accumulated investment memory: why a company is owned or watched, what claims support the thesis, what evidence contradicts it, and what changed over time.

Nothing in this app is financial advice. Market data may be delayed or incomplete depending on each provider.

## Product Principle

CavaAI must treat the thesis and memory as the center of the product. Quantitative valuation is only one tool. No universal model, metric, or score should be forced onto a company when it is not appropriate.

See [docs/PRODUCT_VISION.md](docs/PRODUCT_VISION.md) for the full product direction.

## Stack

Frontend:
- Next.js 16 App Router
- React 19
- TypeScript
- Tailwind CSS v4
- shadcn/ui and Radix primitives

App data and auth:
- Better Auth
- MongoDB and Mongoose
- Finnhub, FMP, Twelve Data, Alpha Vantage and other optional market data providers

Research engine:
- FastAPI
- PostgreSQL and SQLAlchemy
- Qdrant for semantic retrieval
- MinIO for raw documents
- DuckDB for analytics
- Redis and Dramatiq for jobs/cache
- Langfuse optional observability

## Current Capabilities

- Email/password auth
- Portfolio and watchlist
- Company pages and market widgets
- Research OS backend with companies, financial facts, thesis versions, source audits and valuation engines
- Persistent claims, claim evidence, thesis sections, research sessions and company memory
- Source-aware company chat with memory retrieval, user-directed memory write-back and typed source provenance
- Company Research page connected to backend claims, support/contradiction evidence, document/chunk evidence links and memory capture
- What Changed records for manual thesis updates, automatic claim contradictions and material news
- News feed batch ingestion with dedupe and material thesis-change creation
- Document ingestion for TXT/MD/HTML/PDF/DOCX/XLSX/CSV/TSV with checksum, raw storage, chunk metadata and duplicate detection
- Traceable calculated metrics with formula, source fact ids, numerator/denominator, calculation trace, confidence and unavailable states
- Valuation engines for standard DCF, SOTP, pre-revenue/speculative, holding-company and commodity models
- Knowledge/document upload path
- Portfolio analytics and risk endpoints
- News, ProPicks and AI-assisted analysis flows

## Quick Start

Docker local stack:

```bash
cp docker.env.example .env
# edit .env and add the keys you want to use
docker compose up --build
```

Frontend only:

```bash
npm install
npm run dev
```

Backend only:

```bash
cd data-engine
pip install -r requirements.txt
pip install -e .[test]
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Open http://localhost:3000.

## Environment

Minimum local `.env`:

```env
NODE_ENV=development
MONGODB_URI=mongodb://root:example@localhost:27017/jlcavaai?authSource=admin
BETTER_AUTH_SECRET=replace_with_a_32_char_minimum_secret
BETTER_AUTH_URL=http://localhost:3000
FMP_BACKEND_URL=http://localhost:8000
```

Market data:

```env
FINNHUB_API_KEY=
FINNHUB_BASE_URL=https://finnhub.io/api/v1
FMP_API_KEY=
TWELVE_DATA_API_KEY=
ALPHA_VANTAGE_API_KEY=
POLYGON_API_KEY=
NEWSAPI_KEY=
MARKETAUX_API_KEY=
FRED_API_KEY=
TRADING_ECONOMICS_API_KEY=
SEC_USER_AGENT=CavaAI/0.1 contact@example.com
QUARTR_API_KEY=
```

AI:

```env
GEMINI_API_KEY=
GOOGLE_API_KEY=
GEMINI_MODEL=gemini-3.5-flash
GEMINI_CHEAP_MODEL=gemini-2.5-flash-lite
GEMINI_DEEP_MODEL=gemini-3.5-flash
OPENROUTER_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
CAVAAI_ENABLE_VECTOR_CHAT=0
CAVAAI_ENABLE_VECTOR_INGEST=0
CAVAAI_USE_DOCLING=0
```

Email:

```env
NODEMAILER_EMAIL=
NODEMAILER_PASSWORD=
```

Generate a production auth secret with:

```bash
openssl rand -base64 32
```

## Verification

Frontend:

```bash
npm run lint
npm run build
```

Backend:

```bash
cd data-engine
python -m pytest
```

`npm run lint` is configured as a gate for errors. Existing legacy typing and React Compiler cleanup are currently warnings and should be paid down incrementally.

## AI Provider Guidance

For now, use Gemini directly for the app because the code already integrates Google's API and Gemini has very low-cost tiers for extraction/classification. Keep model selection task-based:

- Cheap extraction/classification: `GEMINI_CHEAP_MODEL`
- Normal app analysis/chat: `GEMINI_MODEL`
- Deep research/red-team: `GEMINI_DEEP_MODEL`

OpenRouter is useful once provider abstraction is added because it gives routing/fallback across many models with pay-as-you-go credits. Muse Spark should not be the primary integration target yet: Meta has announced Muse Spark developer availability, but public API pricing/provider coverage is still not mature enough to build the app around it.

## Production Notes

- Do not expose database ports publicly outside local development.
- Do not use placeholder secrets in shared or production environments.
- Run Alembic migrations and seed jobs explicitly in production instead of relying on app startup side effects.
- Keep source lineage for every important financial fact, claim, calculation and thesis update.
- The current `/api/memory`, `/api/chat` and `/api/sources/documents/ingest-*` surfaces are ready for product integration and have tests. Production still needs auth/tenant scoping, richer source previews, automatic evidence extraction and LLM synthesis over the source-aware context before it should be considered finished.

## License

Copyright 2025 Nicolas Iglesias Garcia. All rights reserved.
