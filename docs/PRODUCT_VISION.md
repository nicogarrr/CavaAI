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

## Development Priorities

### P0

- Persistent company memory: backend model, API and company page read/write path are in place.
- Thesis versions: backend generation, history and frontend display are in place.
- Claim memory: unified claim/evidence model, API, migration and company page capture are in place.
- Source lineage: documents, chunks, facts, audits and claim evidence links are in place, including claim evidence linked from the company workspace.
- Document ingestion: manual Quartr/text import path is in place.
- Traceable metrics: normalized facts and valuation trace are in place.
- Company and portfolio chat: basic backend chat route is in place.
- News relevance and thesis impact: manual news analyzer, batch feed ingestion, event storage, dedupe and automatic thesis-change creation for material updates are in place.
- What Changed: thesis change records, manual capture, automatic claim-contradiction changes and material-news changes are in place.

### P1

- Peer comparison
- Moat framework
- Thesis dependency graph
- Red team
- What Changed automation from filings, earnings and fully scheduled external news connectors
- Earnings workflow
- Contradiction engine

### Remaining Work To Feel Complete

- Build a first-class company workspace UI around thesis sections, claims, evidence, sources, news, risks and chat instead of keeping some features as backend-only APIs.
- Add richer source previews and one-click evidence extraction from document/chunk text.
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
