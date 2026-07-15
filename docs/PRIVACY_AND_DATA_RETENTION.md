# Financial Document Privacy and Data Retention

CavaAI treats uploaded filings, earnings material, research notes, portfolio data and generated theses as private financial research data. Data is tenant-scoped in PostgreSQL and object storage; one tenant must never be able to query another tenant's records or document objects.

## Processing policy

- Documents are used only to provide the research, extraction, retrieval and monitoring features requested by the authenticated tenant.
- Raw documents and extracted chunks are not sold or used to train shared models.
- When an external LLM provider is enabled, only the minimum retrieved excerpts and structured context required for the task are sent. Provider, model, prompt version, retrieval IDs and token usage are recorded in the workflow trace.
- API keys, signed identity headers and document contents must not be written to application logs.
- Human approval is required before an extracted company-specific KPI becomes a canonical financial fact.

## Retention and deletion

The default retention period for financial documents is 2,555 days (seven years), configurable through `FINANCIAL_DOCUMENT_RETENTION_DAYS`. A tenant may delete a document earlier; deletion must remove the original object, chunks, vector entries and pending extraction candidates. Canonical facts already used in a thesis must retain a tombstoned source reference so historical decisions remain auditable.

Tenant deletion is a controlled operation: export on request, revoke access immediately, then remove relational data, object storage and vector data after the configured recovery window. Backups expire under the same retention schedule and are encrypted and access-controlled outside the application runtime.

## Public deployment requirements

Before onboarding external users, the operator must publish the controller identity and contact channel, lawful basis, subprocessors and regions, user rights process, breach-response channel, deletion recovery window and the exact LLM-provider data controls for the deployed configuration. This operational policy is not a substitute for jurisdiction-specific legal review.
