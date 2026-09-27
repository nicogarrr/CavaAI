# Market context data policy

The scheduled global FRED actor runs once daily, fetches six public FRED CSV
series (`MORTGAGE30US`, `DGS10`, `DGS2`, `T10YIE`, `BAMLH0A0HYM2`,
`VIXCLS`) without an API key, then stores dated observations and a snapshot.
Each request asks for the latest 800 rows. This is deliberate cold-start
backfill: VIX and high-yield spreads need at least 127 matched trading dates
(126 train observations and today's filtered observation), so 20 recent
rows would leave the model unavailable for months. The 800-row cap gives
room for holidays, holes, and revisions, and bounds DB work to at most 4,800
CSV observations inspected per run. There are six upstream GETs per day,
not one request per tenant or end-user read. Already-seen unchanged rows
are skipped; changed values append a new observation vintage. No periodic
deletion or compaction is performed because deleting a vintage breaks
historic knowledge-time replay and snapshot evidence IDs. Growth is bounded
by six observations per available date plus any actual revisions, rather than
six times 800 daily inserts. An unusually high revision rate warrants an
explicit maintenance decision, not silent pruning.

FRED CSV carries observation dates and values, not release timestamps or
revision history. `fetched_at` means the value was first seen by this app,
not when FRED originally released it. Initial backfilled values are current
vintages applied to old observation dates; they must **not** be presented as
point-in-time historical signals from before ingestion. The model trains on
currently known observations and filters its latest state without future
smoothing. Historical claims before `fetched_at` remain unavailable. Missing
or stale metrics show `sin datos`, and the top-10 S&P concentration remains
unavailable until a complete dated, sourced constituent/cap feed exists.
