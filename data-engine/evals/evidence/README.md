# Evidence contract, phase 1

`evidence_v1.json` is a versioned **synthetic adversarial** set, not measured
quality on real companies or a calibration sample. Run without a provider:

```sh
python data-engine/scripts/run_evidence_evals.py
cd data-engine
python -m pytest tests/test_evidence_contract.py
```

The runner invokes `app.services.evidence_contract`, the same boundary used by
new company-document and knowledge-document ingestion. Pytest runs it in the
normal backend CI suite; a failing case fails that suite. Negative controls
must reject for the declared reason, not merely throw any exception.

## Ledger and trust boundary

New imports store one `metadata.evidence_contract` record per document in the
existing JSON column. Chunks carry `evidence_source_id` and `evidence_chunk_id`.
IDs contain tenant, document namespace/ID and immutable byte hash. A reimport
with identical bytes keeps the existing record. Changed bytes get a new version.
There is no migration, network call, paid provider or frontend change here.

Every record names URL, author, publication date, language, rights, byte hash,
version, tenant, category and original chunk text/hash. Missing values remain
null/`und`/`unknown`; a fetch timestamp is not a publication date. Public access
is not treated as redistribution permission. Anonymous legacy/test ingestion
is explicitly `tenant_unbound`, not silently assigned to a tenant; it cannot
be loaded as a valid `EvidenceSource`. Existing imported documents are NOT
backfilled by this patch.

Routing is conservative: filings are candidate reported evidence, news is a
publisher assertion, letters/books/papers are methodology, personal notes are
user contributions, unknown types stay unclassified. None of these labels
verifies authorship or a number. Ingestion always creates **unreviewed** sources
with **zero reported observations**. A later reviewed extraction adapter must
supply verified observations and exact original citations before reported
claims can pass. Never accept LLM-authored `review_status` as review authority.

Original and translated text share the same source/chunk identity. Use
`attach_translation` with an explicit tenant and original ID. The original
hash and fact citations do not change; translations are not extra sources.
No automatic translation service is added or connected in this patch.

## Gates and limits

- Exact source/chunk/variant IDs and verbatim quote must exist.
- Reported numbers must match an admitted observation and all entity/metric/
  period/unit/currency/share-basis fields, including negative cash flow.
- Observations require verified filings, complete chunks, original text and an
  explicit numeric literal in their quote. V1 does not guess locale separators,
  scale conversions or formulae. Derived claims fail closed until an executor
  is available.
- Contradictory verified observations in the same dimension block a single
  reported value. Older facts cannot be silently relabeled as a current period.
- Inference cannot occupy a factual slot, claim a reported fact ID or replace
  real data. It can be a labeled scenario with a method and refutation condition.
- Confidence is `no calibrada`; percentages are rejected. Ranges must be finite
  and ordered. A huge scenario range can remain exploratory; passing this
  contract does **not** approve its economic plausibility or publication.
- Text, including malicious instructions, is only data. The runner performs no
  instructions, tool calls or side effects from PDF/news text.
- Registry construction and translation reject cross-tenant data, even if a
  caller already applied a SQL/RAG filter.

This is a typed evidence foundation and deterministic boundary evaluation,
not a thesis generator, semantic entailment judge, universal news ledger or
proof that an LLM resists prompt injection. It does not sanitize source prose,
validate every numeral in a natural-language thesis, certify the reviewer,
recompute derived values, impose a universal freshness threshold, rebuild RAG
or change valuation/publication guards. Completeness follows parser metadata;
unmarked truncation cannot be inferred here. Financial connectors/news-event
persistence and retrieval projections need explicit adapters in later small
PRs. No existing factual data is overwritten.
