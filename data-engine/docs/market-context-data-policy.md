# Market context data policy

## Scheduled global FRED actor

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
or stale metrics show `sin datos`.

## Top-10 S&P 500 concentration: dated snapshot, no look-ahead

The top-10 concentration is no longer permanently unavailable. It is
sustained by the index provider's own monthly factsheet, read from a dated
snapshot on disk, and gated by that snapshot's vintage.

**Source.** S&P Dow Jones Indices, *S&P 500 Index Factsheet*
(`https://www.spglobal.com/spdji/en/indices/equity/sp-500/`, consulted
2026-10-01). The factsheet is free and needs no key, and the block
"Index Characteristics" states `NUMBER OF CONSTITUENTS`,
`WEIGHT LARGEST CONSTITUENT [%]`, `WEIGHT TOP 10 CONSTITUENTS [%]` and the
aggregate market-cap statistics, dated with the document's own
`AS OF <month> <day>, <year>`. `source_tier` is
`index_provider_official`: for the composition and the weights of the
S&P 500, the index administrator is the primary source, not an aggregator.
It is not a US federal source (SEC/Treasury publish no index composition),
and the search of the alternatives is recorded in the report: SEC EDGAR has
no index-membership feed, and the free mirrors of the constituent table
(ODC-PDDL / CC BY-SA) are derived from the same factsheet, so they add no
independence and no better licensing.

**Provenance of the retrieval is declared, never implied.** Each snapshot
records the canonical `source_url`, the `retrieved_from` URL actually used and
the `document_sha256`, so a file obtained from a mirror is identifiable as
such. A snapshot built from a mirror is a starting point: rebuild it from the
official download before relying on it.

**Licensing posture, stated plainly.** The factsheet is a free download but it
carries `FOR USE WITH INSTITUTIONS ONLY, NOT FOR USE WITH RETAIL INVESTORS`
and S&P DJI reserves redistribution. This app therefore persists **only the
aggregate index characteristics plus their citation**: no PDF, no
constituent-level weight table, no per-constituent data.
`source_scope` is `aggregate_index_characteristics_only` and the connector
refuses to expose a per-constituent weight. Enabling the feature in a
deployment is an operator decision recorded per environment, and any snapshot
built from a mirror should be rebuilt from the official download before it is
trusted.

**Weights are taken, never derived.** `weight_top_ten_pct` is copied as
published (one decimal, float-adjusted). It is not recomputed from prices or
share counts, and the metric publishes no list of the ten constituents,
because the free source does not publish their weights. When a snapshot
carries composition but no weights the answer is
`index_weights_not_published_by_source`, never an equal-weight or
market-cap approximation standing in for the index weight.

**Vintage rule.** A snapshot answers only for dates `>= its own as_of`. For a
date before the snapshot's `as_of` the response is `sin datos` with reason
`snapshot_vintage_after_requested_date`, and it carries the two dates and the
source URL so the refusal is traceable. The present is never applied to the
past: ingesting the August factsheet today does not describe July.

**Staleness rule.** The factsheet is published monthly at month end. A
snapshot older than 45 days relative to the requested date is reported as
`snapshot_too_stale_for_requested_date`, with the age in days, instead of
being served as if it described the requested date.

**Why a disk snapshot, not a call.** The production VM runs on Oracle Cloud
Always Free and its IP is permanently banned by the SEC, so no design may
depend on a vendor answering at read time. The factsheet is downloaded once
where there is network access by
`scripts/build_sp500_factsheet_snapshots.py` and deployed with the app,
exactly as `build_sec_snapshots.py` does for `SEC_SNAPSHOT_DIR`. Reads are
served from the local file: `GET /api/market/regime` reads only the persisted
`market_regime_snapshots` row, so the read path performs no vendor request at
all, and the in-memory cache is keyed by file mtime and size so a rebuilt
snapshot is visible on the next call.

**The data is data, not source.** `/data-engine/data/` is gitignored in this
repo for exactly this reason (the SEC and ESEF snapshots live there too and
are generated by their `build_*_snapshots.py` scripts, then mounted as a
volume in production). The factsheet snapshots are built the same way:

```
python scripts/build_sp500_factsheet_snapshots.py \
    --source-file /tmp/fs-sp-500.pdf \
    --source-url https://www.spglobal.com/spdji/en/indices/equity/sp-500/ \
    --as-of 2026-08-31 --out data/sp500_factsheet_snapshots
```

which writes `data/sp500_factsheet_snapshots/manifest.json` (source, licence,
scope, `synced_at`, and the sha256 of every declared snapshot) plus
`data/sp500_factsheet_snapshots/factsheets/s-p-500-2026-08-31.json`. The
reader is enabled by pointing `SP500_FACTSHEET_SNAPSHOT_DIR` at that
directory. The parser fails closed: no anchor, wrong number of values, a
document date that disagrees with `--as-of`, or a broken index invariant
writes nothing at all.

**Absence is never zero.** Every unavailable state carries `status:
"sin datos"`, `available: false` and a machine-readable `reason`. The
vocabulary is closed and documented, and the tests assert each one:

| `reason` | when |
| --- | --- |
| `snapshot_dir_not_configured` | `SP500_FACTSHEET_SNAPSHOT_DIR` is not set |
| `no_snapshot_in_disk` | the directory exists and has no factsheet |
| `snapshot_vintage_after_requested_date` | every snapshot is newer than the requested date |
| `snapshot_integrity_failed` | undeclared in the manifest, sha256 mismatch, or missing provenance fields |
| `requested_date_invalid` | no valid date to resolve a vintage against |
| `index_weights_not_published_by_source` | the snapshot has composition but no index weights |
| `snapshot_too_stale_for_requested_date` | the snapshot is older than the staleness window |

**Opt-in, not default.** The reader is enabled only when
`SP500_FACTSHEET_SNAPSHOT_DIR` points at a snapshot directory, the same
opt-in pattern as `SEC_SNAPSHOT_DIR`. A deployed file never silently becomes
"valid for any date" because of where it happens to live.

## Worked example: what may be claimed for a given date

Using the snapshots that the build script produces from the published
factsheets (vintages `as_of` 2026-06-30 with a 36.4% top-10 weight and
`as_of` 2026-08-31 with 37.8%, both ingested 2026-10-01) and a request for
2026-09-20:

* **May be claimed:** "the top 10 constituents of the S&P 500 accounted for
  37.8% of the float-adjusted index on 2026-08-31, the newest factsheet
  published as of 2026-09-20 (S&P DJI factsheet, 503 constituents, largest
  constituent 8.1%)."
* **May be claimed:** "as of 2026-07-15 the top-10 share was 36.4%" — the
  June snapshot was the one current at that date, and it is selected by
  vintage, not by recency.
* **May not be claimed:** anything about 2026-05-15. The answer is
  `snapshot_vintage_after_requested_date`; there is no number, and no
  backfill of the June or August weight into May.
* **May not be claimed:** which ten companies they were. The free source does
  publish their symbols, but not their weights, and the weights are the
  licensed part; the app serves the aggregate and says so.
* **May not be claimed:** a daily S&P 500 concentration series. The source is
  monthly, so any request for an intra-month figure is served with the
  month-end vintage's `as_of` shown next to it, or refused as stale.
