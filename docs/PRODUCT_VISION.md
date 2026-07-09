# CavaAI Product Vision

## Non-negotiable Principle

CavaAI must treat the thesis and memory as the core of the product. Quantitative valuation is an additional tool, not the center of the system. No framework, metric, score, or model should be forced onto a company when it is not appropriate.

## Product Direction

CavaAI is a private Personal Investment Research OS. It should help the investor preserve memory, contrast evidence, monitor thesis changes, and think better over time.

It should not become a generic stock screener, a DCF factory, an auto-trading bot, or a thin LLM wrapper without durable memory.

## Core Objects

- Company workspace
- Thesis and thesis versions
- Thesis sections
- Claims and claim evidence
- Documents and chunks
- Source lineage
- Financial facts and calculated metrics
- News items and thesis impact
- Research sessions
- Conversation memory
- Portfolio positions and alerts

## Target Company Workspace

Each company should evolve into a living workspace with:

- Overview
- Current thesis
- Thesis history
- What changed
- Key claims
- Metrics and financials
- Documents, filings, calls, and letters
- News and catalysts
- Risks and invalidation conditions
- Moat and competitors
- Peer comparison
- Valuation and scenarios
- Portfolio context
- Sources
- Company chat

## Memory Model

The LLM should not "learn" by changing model weights. It should improve through external persistent memory:

- Structured memory in PostgreSQL
- Document memory in Qdrant and MinIO
- Thesis history
- Claim memory
- Conversation memory
- Evidence graph

Every important answer should distinguish facts, calculations, user assumptions, LLM inference, and unverified claims.

The current backend implements the first production-shaped memory loop:

`chat/query -> retrieve company/portfolio memories -> rank by relevance/importance/recency -> inject into answer context -> optionally write back user-directed memories -> dedupe exact repeats`

This is intentionally lightweight and compatible with Mem0/Graphiti-style evolution. It should remain provider-agnostic until the core product workflows are stable.

## Evidence Rules

Missing data is not an estimated fact. When evidence is insufficient, the system must return `unknown`, `missing`, or `insufficient_data`.

Important claims should link back through:

`Source -> Document -> Chunk -> Fact / Claim -> Thesis Section -> Thesis Version`

## Analysis Rules

Different companies require different frameworks:

- PayPal: FCF, margins, buybacks, branded checkout, take rate, TPV.
- AST SpaceMobile: satellites, launch cadence, MNO agreements, coverage, capex, runway, dilution.
- Brookfield: SOTP, fee-related earnings, carry, holdco debt, insurance, holding discount.
- Rocket Lab: launch, space systems, Neutron, backlog, defense, segment margins.

CavaAI must support configurable frameworks, qualitative reasoning, manual assumptions, and source-tagged metrics.

## LLM Routing

Use different model tiers by task:

- Extraction: cheap model
- Classification: cheap model
- Simple chat: mid-tier model
- Deep research: strong model
- Red team: strong model

The current code supports configurable Gemini models via:

- `GEMINI_MODEL`
- `GEMINI_CHEAP_MODEL`
- `GEMINI_DEEP_MODEL`

Future provider abstraction should support OpenRouter, OpenAI, Anthropic, Google, and any provider with an OpenAI-compatible endpoint.

Vector-backed chat retrieval is opt-in through `CAVAAI_ENABLE_VECTOR_CHAT=1`. The default company chat uses the canonical SQL store first so local development and tests do not depend on Qdrant or embedding downloads.

## External OSS Integration Map

- Mem0: use the architecture pattern of extract, retrieve, consolidate and write memory. Do not make it a hard dependency until tenant scoping, cost controls and observability are stable.
- Graphiti: use as the reference pattern for future temporal knowledge graph work, especially facts that change over time and require provenance.
- EdgarTools: preferred P0 candidate for SEC filings, XBRL statements and filing metadata because it provides a focused Python API around EDGAR data.
- Docling: preferred P0 candidate for PDF/DOCX/XLSX/HTML document parsing, table extraction and layout-aware chunks.
- OpenEDGAR: use patterns for bulk EDGAR archive construction; do not adopt the whole stack unless CavaAI needs a self-hosted SEC archive.
- SEC EDGAR AgentKit/MCP: useful adapter/tool patterns over EDGAR; avoid coupling the app to MCP-only runtime paths.
- FinNLP/FinGPT: mine for financial news/data connector ideas and sentiment datasets; do not make fine-tuning frameworks part of the P0 product.

## Development Priorities

### P0

- Persistent company memory: backend model, API and company page read/write path are in place.
- Memory retrieval and write-back: company/portfolio chat now retrieves relevant memories and stores user-directed chat memories with dedupe.
- Thesis versions: backend generation, history and frontend display are in place.
- Claim memory: unified claim/evidence model, API, migration and company page capture are in place.
- Source lineage: documents, chunks, facts, audits and claim evidence links are in place, including claim evidence linked from the company workspace.
- Source hierarchy: source quality is now classified through formal tiers from regulatory filings to user input, with trust scores and source policy text reused by chat and news.
- Document ingestion: manual Quartr/text import, generic file upload and URL ingestion are in place. Native parsers cover TXT/MD/HTML/PDF/DOCX/XLSX/CSV/TSV with checksum, raw storage, chunk metadata and duplicate detection. Docling can be used as an opt-in parser with `CAVAAI_USE_DOCLING=1`.
- Source evidence workflow: the company workspace shows source chunk previews and supports one-click creation of source-derived claims or support/contradiction evidence linked to existing claims.
- Traceable metrics: normalized facts, valuation trace and calculated metric records are in place. Current canonical calculated metrics include FCF margin, gross/operating/net margin, ROE, ROA, ROIC, FCF conversion and net debt / EBITDA, each with definition version, formula, numerator, denominator, source fact ids, calculation trace, confidence and unavailable status when inputs are missing.
- Company and portfolio chat: backend chat is now source-aware and returns facts, calculations, memory/user assumptions, unverified claims, inference and typed sources.
- News relevance and thesis impact: manual news analyzer, batch feed ingestion, event storage, dedupe, source-tier policy, portfolio-aware materiality and automatic thesis-change creation for material updates are in place.
- What Changed: thesis change records, manual capture, automatic claim-contradiction changes and material-news changes are in place.
- Peer comparison: company workspace comparison now uses same-industry/sector peers and traceable calculated metrics with peer median/average benchmarks.

### P1

- Moat framework
- Thesis dependency graph
- Red team
- What Changed automation from filings, earnings and fully scheduled external news connectors
- Earnings workflow
- Contradiction engine

### Remaining Work To Feel Complete

- Build a first-class company workspace UI around risks and red-team work instead of keeping those features as backend-only APIs.
- Add LLM synthesis on top of source-aware chat context while preserving the current evidence contract.
- Add automatic LLM-assisted evidence extraction suggestions from document/chunk text.
- Promote Docling from optional parser to primary production parser after validating install size, OCR/table accuracy and deployment footprint.
- Expand traceable metrics to CFROI, ROCE, incremental ROIC, share-count CAGR and WACC sourced from market assumptions.
- Implement "What changed" from new filings/news/earnings into `thesis_changes`, not only manual thesis history.
- Add an automated contradiction engine that compares new evidence against existing claims and marks review-required items.
- Add a provider-agnostic LLM interface before expanding beyond Gemini.
- Replace the dynamic `0001_initial` Alembic migration with explicit table definitions before production hardening.
- Pay down legacy frontend warnings currently tolerated by ESLint.
- Add e2e/browser coverage for `/research`, `/research/[ticker]`, source import, thesis generation and memory capture.
- Replace remaining demo/dev fallbacks with explicit production onboarding and empty states.

### P2

- Advanced company-specific valuation models
- Automatic evaluation
- Portfolio factor intelligence
- Scenario calibration

## Success Criterion

CavaAI is working when the user can add a company, upload filings/results/letters, create a thesis, ask source-aware questions, inspect traceable metrics, compare competitors, analyze moat, save hypotheses, receive material news, see whether the thesis changed, inspect sources, and improve the accumulated knowledge over months.
