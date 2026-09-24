"""Genera snapshots EDGAR (formato companyfacts oficial) desde el parquet
espejo de HuggingFace (DenyTranDFW/edgar_xbrl_companyfacts), para el modo
snapshot del conector (SEC_SNAPSHOT_DIR). La SEC bloquea IPs de datacenter;
el espejo replica el companyfacts oficial (validado fila a fila contra la
API directa para AAPL FY25: revenue/OCF/capex identicos).

Uso:
    python scripts/build_sec_snapshots.py --parquet /tmp/usgaap.parquet \
        --out data/sec_snapshots TICKER:CIK [TICKER:CIK ...]

Manifest: {"tickers": {T: cik10}, "fetched_at": <fecha del parquet>,
           "source": "..."} - la procedencia queda declarada, nunca implicita.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import polars as pl

CONCEPTS = [
    "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet", "GrossProfit", "OperatingIncomeLoss",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    "IncomeTaxExpenseBenefit", "InterestExpenseNonOperating",
    "InterestExpense", "NetIncomeLoss", "ProfitLoss",
    "EarningsPerShareDiluted", "WeightedAverageNumberOfDilutedSharesOutstanding",
    "CommonStockSharesOutstanding", "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsAndShortTermInvestments", "LongTermDebt",
    "LongTermDebtNoncurrent", "DebtLongtermAndShorttermCombinedAmount",
    "Assets", "Liabilities", "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "Goodwill", "FiniteLivedIntangibleAssetsNet",
    "IndefiniteLivedIntangibleAssetsExcludingGoodwill",
    "OperatingLeaseLiability", "OperatingLeaseLiabilityNoncurrent",
    "NetCashProvidedByUsedInOperatingActivities",
    "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsOfDividends",
    "PaymentsOfDividendsCommonStock",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--fetched-at", required=True,
                        help="Fecha de los datos del espejo (provenance).")
    parser.add_argument("targets", nargs="+", help="TICKER:CIK (cik a 10 o sin padding)")
    args = parser.parse_args()

    out = Path(args.out)
    (out / "companyfacts").mkdir(parents=True, exist_ok=True)

    targets: dict[str, str] = {}
    for raw in args.targets:
        ticker, cik = raw.split(":")
        targets[ticker.strip().upper()] = cik.strip().zfill(10)

    df = pl.scan_parquet(args.parquet).filter(
        pl.col("item").is_in(CONCEPTS),
        pl.col("source_folder").str.extract(r"CIK(\d{10})").is_in(
            list(targets.values())
        ),
    ).select("item", "end", "fy", "fp", "form", "filed", "unit_type",
             "val_dec", "source_folder").collect()

    for ticker, cik in targets.items():
        sub = df.filter(pl.col("source_folder").str.starts_with(f"CIK{cik}"))
        us_gaap: dict[str, dict] = {}
        for row in sub.iter_rows(named=True):
            concept = us_gaap.setdefault(row["item"], {"units": {}})
            unit = row["unit_type"] or "USD"
            entry = {
                "end": row["end"], "fy": int(row["fy"]) if row["fy"] else None,
                "fp": row["fp"], "form": row["form"], "filed": row["filed"],
                "val": int(row["val_dec"]) if row["val_dec"] is not None else None,
            }
            concept["units"].setdefault(unit, []).append(entry)
        payload = {
            "cik": int(cik), "entityName": ticker,
            "facts": {"us-gaap": us_gaap},
        }
        path = out / "companyfacts" / f"CIK{cik}.json"
        path.write_text(json.dumps(payload))
        n = sum(len(u) for c in us_gaap.values() for u in c["units"].values())
        print(f"{ticker}: {len(us_gaap)} conceptos, {n} entradas -> {path}")

    manifest = {
        "tickers": {t: c for t, c in targets.items()},
        "fetched_at": args.fetched_at,
        "source": "HuggingFace mirror of SEC EDGAR companyfacts "
                  "(DenyTranDFW/edgar_xbrl_companyfacts), validado contra API directa",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print("manifest ->", out / "manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
