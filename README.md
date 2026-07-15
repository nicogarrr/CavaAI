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
- MongoDB only for Better Auth and the legacy watchlist boundary
- PostgreSQL as the canonical store for portfolios, alerts, companies, facts, theses, evidence, models, journals and document metadata
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
- One canonical `/research/[ticker]` company workspace backed by a coherent snapshot contract
- Research OS backend with companies, financial facts, thesis versions, source audits and valuation engines
- Persistent claims, claim evidence, thesis sections, research sessions and company memory
- Source-aware company chat with memory retrieval, user-directed memory write-back and typed source provenance
- Company Research page connected to backend claims, support/contradiction evidence, document/chunk evidence links and memory capture
- Source Evidence Lab for chunk previews, source-derived claim creation and support/contradiction evidence capture from imported documents
- What Changed records for manual thesis updates, automatic claim contradictions and material news
- News feed batch ingestion with dedupe, formal source tiers, portfolio-aware materiality and material thesis-change creation
- Document ingestion for TXT/MD/HTML/PDF/DOCX/XLSX/CSV/TSV with checksum, raw storage, chunk metadata and duplicate detection
- Traceable calculated metrics with formula, source fact ids, numerator/denominator, calculation trace, confidence and unavailable states
- Peer comparison from same-industry/sector companies using traceable calculated metrics and peer median/average benchmarks
- Versioned Long-Term Fundamental Modeling Engine with company-specific drivers, mandatory facts, scenarios, forecasts and source traces
- Dedicated valuation engines for standard DCF, SOTP, pre-revenue/speculative, holding-company, commodity, bank, insurer and REIT models
- Decision Journal and Expectation vs Reality linked to persisted thesis/model versions
- Source/document ingestion path
- Portfolio analytics and risk endpoints
- News impact, deterministic ProPicks and provider-agnostic AI-assisted research flows

## Quick Start

Docker local stack:

```bash
cp docker.env.example .env
# edit .env and add the keys you want to use
docker compose up --build
```

If an older checkout created `jlcava-*` Docker volumes, do not start writing to
the new empty `cavaai-*` volumes. Stop the stack and migrate them explicitly:

```powershell
.\scripts\migrate-docker-volumes.ps1 -DryRun
.\scripts\migrate-docker-volumes.ps1
docker compose up --build
```

The migration refuses to run while CavaAI containers are active and refuses to
overwrite a non-empty target. Verify PostgreSQL, MongoDB, MinIO and Qdrant before
removing any old volume. A new installation may consciously start from empty
`cavaai-*` volumes without running the script.

Operational runbooks:

- [Backup and restore](docs/BACKUP_RESTORE.md)
- [Financial document privacy and retention](docs/PRIVACY_AND_DATA_RETENTION.md)

Authenticated API requests are rate-limited per tenant, user and client address;
expensive LLM and model-refresh routes use a separate lower budget.

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
python -m alembic upgrade head
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Open http://localhost:3000.

## Environment

Minimum local `.env`:

```env
NODE_ENV=development
MONGODB_URI=mongodb://root:example@localhost:27017/cavaai?authSource=admin
NEXT_PUBLIC_SUPPORT_EMAIL=support@cavaai.app
BETTER_AUTH_SECRET=replace_with_a_32_char_minimum_secret
BETTER_AUTH_URL=http://localhost:3000
RESEARCH_AUTH_REQUIRED=true
RESEARCH_AUTH_SECRET=replace_with_an_independent_32_char_research_secret
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
LLM_PROVIDER=auto
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
npm run generate:openapi
git diff --exit-code -- data-engine/openapi.json lib/research/openapi.generated.ts
```

Backend:

```bash
cd data-engine
python -m pytest
```

`npm run lint` is configured as a gate for errors. React Compiler and legacy typing warnings are tracked as quality debt and must not grow.

## AI Provider Guidance

The research engine uses one provider abstraction for OpenRouter, OpenAI-compatible endpoints, Anthropic and Gemini. `LLM_PROVIDER=auto` selects the first enabled provider with a configured key; task-level model overrides keep extraction, synthesis and red-team workloads independent. Provider output never replaces the evidence contract or creates missing financial facts.

## Production Notes

- Do not expose database ports publicly outside local development.
- Do not use placeholder secrets in shared or production environments.
- Run Alembic migrations explicitly in production. The optional seed command installs only the global company taxonomy; it never creates portfolio positions, cash or evidence.
- Keep source lineage for every important financial fact, claim, calculation and thesis update.
- Research APIs require signed tenant/user identity, and tenant-owned rows, workers, chunks and vector operations are scoped to that identity.
- Raw source originals are canonical in MinIO in production; PostgreSQL stores metadata/chunks and Qdrant is a rebuildable semantic index.
- Alembic revisions are explicit and immutable; do not import mutable application metadata from a migration.

## License

Copyright 2025 Nicolas Iglesias Garcia. All rights reserved.
