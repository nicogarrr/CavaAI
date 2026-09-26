"""Fiscal-year tax computation for the private portfolio.

The report follows Spanish IRPF conventions:

- Realized gains/losses use FIFO lot accounting on sells (required by law for
  homogeneous securities). Each buy lot's unit cost includes acquisition fees;
  a deferred wash-sale loss is added separately to preserve that basis. FX
  conversion to the portfolio base currency uses the transaction-date rate
  from the FX ledger.
- Dividends are grouped by company and converted at the payment date rate.
- Withholding is matched from cash transactions whose type contains
  "withholding" / "tax" (IBKR reports gross dividend and withheld tax as
  separate CashTransaction rows in the same statement).
- Wash-sale (art. 33.5.f LIRPF, valores cotizados): a realized loss is NOT
  computable when homogeneous shares are repurchased within two months
  before or after the sale AND those shares remain in the portfolio after
  the sale (Manual Renta 2025, cap. 11, apdo. E: "dichos valores continúan
  en el patrimonio del contribuyente tras la transmisión"; if nothing
  remains, "la pérdida patrimonial podrá imputarse íntegramente").
  Backward repurchases follow the Manual's proportionality: recompra =
  min(remanente tras la venta, comprado en los 2 meses previos), with the
  Manual's single-purchase exception (only one buy op in the prior window
  and zero holdings at its start → no limitation; the initial purchase
  itself is not a repurchase). The blocked loss is absorbed FIFO onto the
  oldest surviving in-window lots' cost basis, so it surfaces when those
  lots are sold. Forward (posterior) repurchases are also taken into
  account ("deben tenerse en cuenta las compras posteriores"),   blocking proportionally up to the posterior buy quantity; the Manual gives no
  explicit posterior prorrata, so this is a documented interpretation.
  Losses whose forward window extends beyond the available data are
  reported as provisionally computable and flagged per sale and in the
  summary. The convention is labeled in the report
  (wash_sale_rule = "es-irpf-2m", wash_sale_basis = "manual-aeat-2025")
  and applies only to this Spanish IRPF report.
  ORIENTATIVO: this report is a working paper ("orientativo, no apto para
  declarar") until signed off by a colegiado fiscal adviser. See
  summary.fiscal_disclaimer.
  Limitation: Company metadata has no ISIN/security identifier or listing
  flag, so the engine cannot prove that a ticker is a listed homogeneous
  security or distinguish dividends from unlisted instruments. No such
  inference is made here.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Company,
    Position,
    TaxReport,
    Transaction,
)
from app.services.portfolio_fx_service import PortfolioFXService

FIFO_METHOD = "fifo"
AVERAGE_METHOD = "average"

# Spanish IRPF wash-sale convention (art. 33.5.f LIRPF, listed securities),
# developed by Manual Renta 2025 cap. 11 apdo. E (procedimiento de recompra):
# homogeneous shares acquired within two months before or after a loss sale
# block the loss only while they remain in the portfolio after the sale,
# proportionally (min(remanente, comprado previo)), absorbed FIFO.
WASH_SALE_RULE_ID = "es-irpf-2m"
WASH_SALE_BASIS = "manual-aeat-2025"
WASH_SALE_WINDOW = relativedelta(months=2)

# Working-paper label: the figures follow the Manual's procedure but the
# ledger has no ISIN/listing proof and no external-broker coverage, so the
# report must be presented as orientativo until a fiscal adviser signs off.
FISCAL_DISCLAIMER = (
    "Informe orientativo, no apto para declarar sin la validación de un "
    "asesor fiscal: wash-sale según procedimiento del Manual AEAT 2025 "
    "(art. 33.5.f LIRPF, proporcionalidad y FIFO); sin ISIN/cotización ni "
    "cobertura multibróker verificadas."
)

DIVIDEND_ACTIONS = {"dividend", "div", "cash_dividend", "withholding"}
SELL_ACTIONS = {"sell", "sold"}
BUY_ACTIONS = {"buy", "bot", "b"}


def _money(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _new_cash_bucket(ticker: str, transaction) -> dict:
    return {
        "ticker": ticker,
        "currency": transaction.currency,
        "dividends_native": Decimal("0"),
        "dividends_base": Decimal("0"),
        "withholding_native": Decimal("0"),
        "withholding_base": Decimal("0"),
        "missing_fx": False,
        "unattributed": False,
        "payments": [],
    }


def _unattributed_label(transaction) -> str:
    """A stable, visible label for cash whose company could not be resolved.

    The symbol is recovered from the raw Flex payload when present so the
    reviewer can see WHICH issuer is unattributed instead of a single opaque
    "unattributed" bucket.
    """
    payload = transaction.raw_payload or {}
    for key, value in payload.items():
        if str(key).lower() in {"symbol", "underlyingsymbol"} and value:
            return f"UNATTRIBUTED:{str(value).strip().upper()}"
    return f"UNATTRIBUTED:{transaction.currency or '???'}:{transaction.action or '?'}"


class TaxReportService:
    """Compute and persist per-fiscal-year tax snapshots."""

    def __init__(self) -> None:
        self.fx = PortfolioFXService()
        self.settings = get_settings()

    def compute_report(self, db: Session, fiscal_year: int) -> dict:
        # SOLO lectura: sin portfolio persistido se usa la divisa por defecto;
        # crearlo aqui convertia cualquier GET del informe en una escritura.
        portfolio = self.fx.portfolio(db)
        base_currency = (portfolio.base_currency if portfolio else "EUR") or "EUR"

        start = date(fiscal_year, 1, 1)
        end = date(fiscal_year, 12, 31)

        # outerjoin, not join: a cash row with company_id NULL (an IBKR
        # dividend or retention whose symbol could not be resolved) is real
        # taxable income. The INNER JOIN dropped it silently, so the report
        # declared zero dividends with no flag anywhere.
        rows = db.execute(
            select(Transaction, Company)
            .outerjoin(Company, Transaction.company_id == Company.id)
            .where(Transaction.trade_date >= start, Transaction.trade_date <= end)
            .order_by(Transaction.trade_date, Transaction.id)
        ).all()

        dividends_by_company: dict[str, dict] = {}
        realized_by_company: dict[str, dict] = {}
        misc_rows: list[dict] = []

        # First pass: dividends, withholding and misc cash movements.
        for transaction, company in rows:
            action = (transaction.action or "").lower()
            if company is None:
                # Taxable cash with no resolvable company (an IBKR dividend or
                # retention whose symbol is not in the workspace). It must not
                # disappear: it is income, and hiding it produces a filing that
                # understates the taxable base with no flag.
                if not (
                    action in DIVIDEND_ACTIONS
                    or "dividend" in action
                    or "withholding" in action
                    or "interest" in action
                    or "fee" in action
                    or action == "cash_misc"
                ):
                    continue
                ticker = _unattributed_label(transaction)
                if ticker not in dividends_by_company:
                    dividends_by_company[ticker] = _new_cash_bucket(ticker, transaction)
                dividends_by_company[ticker]["unattributed"] = True
            else:
                ticker = company.ticker
            if action in DIVIDEND_ACTIONS or "dividend" in action or "withholding" in action:
                rate = self.fx.rate(
                    db,
                    quote_currency=transaction.currency,
                    base_currency=base_currency,
                    as_of=transaction.trade_date,
                )
                gross = transaction.price if transaction.price else transaction.quantity
                amount_native = gross
                # Never convert at par: without a real FX rate the base
                # amount is unknown and must stay None.
                amount_base = amount_native * rate if rate is not None else None
                bucket = dividends_by_company.setdefault(
                    ticker, _new_cash_bucket(ticker, transaction)
                )
                if company is None:
                    bucket["unattributed"] = True
                if "withholding" in action or "tax" in action:
                    withheld = abs(amount_native)
                    bucket["withholding_native"] += withheld
                    if amount_base is not None:
                        bucket["withholding_base"] += abs(amount_base)
                    else:
                        bucket["missing_fx"] = True
                    bucket["payments"].append(
                        {
                            "date": transaction.trade_date.isoformat(),
                            "type": "withholding",
                            "amount_native": _money(withheld),
                            "amount_base": _money(abs(amount_base)) if amount_base is not None else None,
                        }
                    )
                else:
                    bucket["dividends_native"] += amount_native
                    if amount_base is not None:
                        bucket["dividends_base"] += amount_base
                    else:
                        bucket["missing_fx"] = True
                    bucket["payments"].append(
                        {
                            "date": transaction.trade_date.isoformat(),
                            "type": "dividend",
                            "amount_native": _money(amount_native),
                            "amount_base": _money(amount_base),
                        }
                    )
                continue

            if action in {"interest", "fee", "cash_misc"}:
                rate = self.fx.rate(
                    db,
                    quote_currency=transaction.currency,
                    base_currency=base_currency,
                    as_of=transaction.trade_date,
                )
                amount = transaction.price or transaction.quantity
                misc_rows.append(
                    {
                        "date": transaction.trade_date.isoformat(),
                        "ticker": ticker,
                        "type": action,
                        "amount_native": _money(amount),
                        "amount_base": _money(amount * rate) if rate else None,
                        "currency": transaction.currency,
                    }
                )
                continue

            if action in SELL_ACTIONS or action in BUY_ACTIONS:
                # Accumulate for FIFO pass; done below in chronological order.
                continue

        # Second pass: FIFO realized gains/losses per company, with the
        # two-month wash-sale rule. Lots are rebuilt from the FULL
        # transaction history so cost basis and deferred losses stay correct
        # across fiscal years; only sales inside [start, end] enter the
        # report (a prior-year sale must never leak into this year's totals).
        #
        # Documented procedure (Manual Renta 2025, cap. 11, apdo. E):
        # - Backward: prior-window buys block only for the shares still held
        #   at sale time, proportionally as min(remanente, comprado previo),
        #   absorbed FIFO onto the oldest surviving in-window lots. Single
        #   prior buy op with zero holdings at the window start is the initial
        #   purchase, not a repurchase → no limitation.
        # - Forward: posterior-window buys are also taken into account and
        #   block proportionally up to the posterior buy quantity (the Manual
        #   gives no explicit posterior prorrata: documented interpretation).
        # - A partial repurchase blocks the loss proportionally.
        # - When a sale's forward window extends beyond the latest available
        #   transaction, the unblocked remainder is reported as provisionally
        #   computable and flagged (wash_sale_window_open).
        # The FIFO pass only needs buy/sell legs, which always carry a company;
        # an INNER JOIN here is correct and keeps unattributed cash out of the
        # lot rebuild (it is handled and reported in the first pass).
        tx_rows = db.execute(
            select(Transaction, Company)
            .join(Company, Transaction.company_id == Company.id)
            .order_by(Transaction.trade_date, Transaction.id)
        ).all()

        last_data_date = tx_rows[-1][0].trade_date if tx_rows else end

        events_by_ticker: dict[str, list] = {}
        for transaction, company in tx_rows:
            events_by_ticker.setdefault(company.ticker, []).append(transaction)

        realized_by_company = {}
        for ticker, events in events_by_ticker.items():
            lots: deque[dict] = deque()
            open_loss_sales: list[dict] = []
            year_sales: list[dict] = []
            # Chronological buy/sell history for this ticker, used ONLY for
            # the Manual AEAT 2025 backward proportionality
            # (min(remanente, comprado previo) + single-purchase exception).
            prior_buys: list[tuple] = []  # (trade_date, quantity)
            prior_sells: list[tuple] = []  # (trade_date, quantity)
            for transaction in events:
                action = (transaction.action or "").lower()
                if action in BUY_ACTIONS:
                    if transaction.quantity is None or transaction.quantity <= 0:
                        # Ingesta: lotes de compra sin cantidad positiva se
                        # rechazan (nunca entran a la base de coste).
                        continue
                    acquisition_cost = transaction.quantity * transaction.price + transaction.fees
                    lot = {
                        "qty": transaction.quantity,
                        "unit": (
                            acquisition_cost / transaction.quantity
                            if transaction.quantity
                            else Decimal("0")
                        ),
                        "deferred": Decimal("0"),
                        "capacity": transaction.quantity,
                        "date": transaction.trade_date,
                    }
                    # Forward window: this buy can repurchase earlier loss sales.
                    still_open: list[dict] = []
                    for sale in open_loss_sales:
                        if transaction.trade_date > sale["date"] + WASH_SALE_WINDOW:
                            continue  # forward window closed
                        if sale["qty_unblocked"] > 0 and lot["capacity"] > 0:
                            take = min(lot["capacity"], sale["qty_unblocked"])
                            lot["deferred"] += take * sale["loss_per_share"]
                            lot["capacity"] -= take
                            sale["blocked_qty"] += take
                            sale["qty_unblocked"] -= take
                        still_open.append(sale)
                    open_loss_sales = still_open
                    lots.append(lot)
                    prior_buys.append((transaction.trade_date, transaction.quantity))
                    continue
                if action not in SELL_ACTIONS:
                    continue

                if transaction.quantity is None or transaction.quantity <= 0:
                    # Ingesta: ventas sin cantidad positiva se rechazan.
                    continue
                remaining = transaction.quantity
                proceeds_native = transaction.quantity * transaction.price - transaction.fees
                cost_native = Decimal("0")
                while remaining > Decimal("0") and lots:
                    lot = lots[0]
                    take = min(lot["qty"], remaining)
                    cost_native += take * lot["unit"]
                    if lot["deferred"] > 0 and lot["qty"] > 0:
                        deferred_take = lot["deferred"] * take / lot["qty"]
                        cost_native += deferred_take
                        lot["deferred"] -= deferred_take
                    lot["qty"] -= take
                    if lot["qty"] == 0:
                        lots.popleft()
                    remaining -= take
                # Over-sell: se vendió más de lo comprado. El remanente se
                # valora a coste cero pero se MARCA con warning explícito en
                # vez de registrar una ganancia silenciosa.
                over_sell_quantity = remaining if remaining > Decimal("0") else Decimal("0")
                over_sell = over_sell_quantity > 0

                gain_native = proceeds_native - cost_native
                if gain_native < 0:
                    sale = {
                        "date": transaction.trade_date,
                        "qty_unblocked": transaction.quantity,
                        "loss_per_share": -gain_native / transaction.quantity,
                        "blocked_qty": Decimal("0"),
                    }
                    # Backward window (Manual Renta 2025, apdo. E.1): prior-window
                    # buys block only for the shares still held, proportionally:
                    #   recompra = min(remanente tras la venta,
                    #                  comprado en los 2 meses previos),
                    # absorbed FIFO onto the oldest surviving in-window lots.
                    # Exception: a single buy op in the prior window with zero
                    # holdings at its start is the initial purchase itself,
                    # not a repurchase → no limitation.
                    window_start = transaction.trade_date - WASH_SALE_WINDOW
                    bought_prev = Decimal("0")
                    buy_ops_prev = 0
                    for buy_date, buy_qty in prior_buys:
                        if buy_date >= window_start:
                            bought_prev += buy_qty
                            buy_ops_prev += 1
                    holdings_before_window = Decimal("0")
                    for buy_date, buy_qty in prior_buys:
                        if buy_date < window_start:
                            holdings_before_window += buy_qty
                    for sell_date, sell_qty in prior_sells:
                        if sell_date < window_start:
                            holdings_before_window -= sell_qty
                    if holdings_before_window < 0:
                        holdings_before_window = Decimal("0")
                    remaining_after = sum(lot["qty"] for lot in lots)
                    if buy_ops_prev == 1 and holdings_before_window <= 0:
                        recompra_prev_qty = Decimal("0")
                    else:
                        recompra_prev_qty = min(
                            remaining_after, bought_prev, sale["qty_unblocked"]
                        )
                    to_block = recompra_prev_qty
                    for lot in lots:
                        if to_block <= 0 or sale["qty_unblocked"] <= 0:
                            break
                        if lot["date"] < window_start or lot["capacity"] <= 0 or lot["qty"] <= 0:
                            continue
                        take = min(lot["capacity"], lot["qty"], to_block, sale["qty_unblocked"])
                        lot["deferred"] += take * sale["loss_per_share"]
                        lot["capacity"] -= take
                        sale["blocked_qty"] += take
                        sale["qty_unblocked"] -= take
                        to_block -= take
                    prior_sells.append((transaction.trade_date, transaction.quantity))
                    open_loss_sales.append(sale)
                else:
                    sale = None

                if start <= transaction.trade_date <= end:
                    year_sales.append(
                        {
                            "transaction": transaction,
                            "proceeds_native": proceeds_native,
                            "cost_native": cost_native,
                            "gain_native": gain_native,
                            "sale": sale,
                            "over_sell": over_sell,
                            "over_sell_quantity": over_sell_quantity,
                        }
                    )

            # Aggregate the bucket only after the full event loop so that
            # forward-window repurchases (which can postdate the sale) are
            # reflected in the blocked amounts.
            if not year_sales:
                continue
            bucket = realized_by_company.setdefault(
                ticker,
                {
                    "ticker": ticker,
                    "currency": year_sales[0]["transaction"].currency,
                    "proceeds_native": Decimal("0"),
                    "cost_native": Decimal("0"),
                    "gain_native": Decimal("0"),
                    "gain_base": Decimal("0"),
                    "blocked_loss_native": Decimal("0"),
                    "blocked_loss_base": Decimal("0"),
                    "missing_fx": False,
                    "wash_sale_window_open": False,
                    "sale_count": 0,
                    "over_sell_count": 0,
                    "over_sell": False,
                    "sales": [],
                },
            )
            for entry in year_sales:
                transaction = entry["transaction"]
                sale = entry["sale"]
                blocked_native = (
                    sale["blocked_qty"] * sale["loss_per_share"]
                    if sale is not None
                    else Decimal("0")
                )
                computable_native = entry["gain_native"] + blocked_native
                window_open = bool(
                    sale is not None
                    and sale["qty_unblocked"] > 0
                    and sale["date"] + WASH_SALE_WINDOW > last_data_date
                )
                rate = self.fx.rate(
                    db,
                    quote_currency=transaction.currency,
                    base_currency=base_currency,
                    as_of=transaction.trade_date,
                )
                if rate is not None:
                    computable_base = computable_native * rate
                    blocked_base = blocked_native * rate
                else:
                    computable_base = None
                    blocked_base = None
                bucket["proceeds_native"] += entry["proceeds_native"]
                bucket["cost_native"] += entry["cost_native"]
                bucket["gain_native"] += computable_native
                bucket["blocked_loss_native"] += blocked_native
                if computable_base is not None:
                    bucket["gain_base"] += computable_base
                    bucket["blocked_loss_base"] += blocked_base
                else:
                    bucket["missing_fx"] = True
                bucket["wash_sale_window_open"] = bucket["wash_sale_window_open"] or window_open
                bucket["sale_count"] += 1
                if entry["over_sell"]:
                    bucket["over_sell"] = True
                    bucket["over_sell_count"] += 1
                bucket["sales"].append(
                    {
                        "date": transaction.trade_date.isoformat(),
                        "quantity": float(transaction.quantity),
                        "proceeds_native": _money(entry["proceeds_native"]),
                        "cost_native": _money(entry["cost_native"]),
                        "gain_native": _money(computable_native),
                        "gain_base": _money(computable_base) if computable_base is not None else None,
                        "raw_gain_native": _money(entry["gain_native"]),
                        "blocked_loss_native": _money(blocked_native),
                        "blocked_loss_base": _money(blocked_base) if blocked_base is not None else None,
                        "wash_sale_blocked": blocked_native > 0,
                        "wash_sale_window_open": window_open,
                        "over_sell": bool(entry["over_sell"]),
                        "over_sell_quantity": float(entry["over_sell_quantity"]),
                        "warning": (
                            "over_sell: sold more shares than the recorded lots; "
                            "excess valued at zero cost, verify the ledger"
                            if entry["over_sell"]
                            else None
                        ),
                    }
                )

        dividends = []
        for bucket in dividends_by_company.values():
            dividends.append(
                {
                    "ticker": bucket["ticker"],
                    "currency": bucket["currency"],
                    "dividends_native": _money(bucket["dividends_native"]),
                    "dividends_base": None if bucket["missing_fx"] else _money(bucket["dividends_base"]),
                    "withholding_native": _money(bucket["withholding_native"]),
                    "withholding_base": None if bucket["missing_fx"] else _money(bucket["withholding_base"]),
                    "missing_fx": bucket["missing_fx"],
                    "unattributed": bucket.get("unattributed", False),
                    "payments": bucket["payments"],
                }
            )

        realized = []
        for bucket in realized_by_company.values():
            realized.append(
                {
                    "ticker": bucket["ticker"],
                    "currency": bucket["currency"],
                    "proceeds_native": _money(bucket["proceeds_native"]),
                    "cost_native": _money(bucket["cost_native"]),
                    "gain_native": _money(bucket["gain_native"]),
                    "gain_base": None if bucket["missing_fx"] else _money(bucket["gain_base"]),
                    "blocked_loss_native": _money(bucket["blocked_loss_native"]),
                    "blocked_loss_base": None if bucket["missing_fx"] else _money(bucket["blocked_loss_base"]),
                    "wash_sale_window_open": bucket["wash_sale_window_open"],
                    "missing_fx": bucket["missing_fx"],
                    "sale_count": bucket["sale_count"],
                    "over_sell": bucket["over_sell"],
                    "over_sell_count": bucket["over_sell_count"],
                    "sales": bucket["sales"],
                }
            )

        dividend_incomplete = any(b["missing_fx"] for b in dividends)
        realized_incomplete = any(b["missing_fx"] for b in realized)
        incomplete_fx = dividend_incomplete or realized_incomplete

        total_dividends = sum(
            (Decimal(str(b["dividends_base"] or 0)) for b in dividends), Decimal("0")
        )
        total_withholding = sum(
            (Decimal(str(b["withholding_base"] or 0)) for b in dividends), Decimal("0")
        )
        total_gain = sum(
            (Decimal(str(b["gain_base"] or 0)) for b in realized), Decimal("0")
        )
        total_blocked = sum(
            (Decimal(str(b["blocked_loss_base"] or 0)) for b in realized), Decimal("0")
        )

        summary = {
            "fiscal_year": fiscal_year,
            "base_currency": base_currency,
            # Totals stay None when any component could not be converted:
            # a partial total would look authoritative and be wrong.
            "total_dividends_base": None if dividend_incomplete else _money(total_dividends),
            "total_withholding_base": None if dividend_incomplete else _money(total_withholding),
            "total_realized_gain_base": None if realized_incomplete else _money(total_gain),
            "total_blocked_loss_base": None if realized_incomplete else _money(total_blocked),
            "wash_sale_rule": WASH_SALE_RULE_ID,
            "wash_sale_basis": WASH_SALE_BASIS,
            "fiscal_disclaimer": FISCAL_DISCLAIMER,
            "wash_sale_window_open": sorted(
                b["ticker"] for b in realized if b["wash_sale_window_open"]
            ),
            "net_taxable_base": None if incomplete_fx else _money(total_dividends + total_gain),
            "dividend_count": len(dividends),
            "unattributed_tickers": sorted(
                b["ticker"] for b in dividends if b.get("unattributed")
            ),
            "unattributed_dividends_base": _money(
                sum(
                    (
                        Decimal(str(b["dividends_base"] or 0))
                        for b in dividends
                        if b.get("unattributed")
                    ),
                    Decimal("0"),
                )
            ),
            "sell_count": sum(b["sale_count"] for b in realized),
            "over_sell": sorted(
                b["ticker"] for b in realized if b.get("over_sell")
            ),
            "method": FIFO_METHOD,
            "incomplete_fx": incomplete_fx,
            "missing_fx": sorted(
                {b["ticker"] for b in dividends if b["missing_fx"]}
                | {b["ticker"] for b in realized if b["missing_fx"]}
            ),
        }

        return {
            "summary": summary,
            "dividends": sorted(dividends, key=lambda d: d["ticker"]),
            "realized": sorted(realized, key=lambda d: d["ticker"]),
            "misc": sorted(misc_rows, key=lambda d: d["date"]),
        }

    def get_report(self, db: Session, fiscal_year: int) -> dict:
        """Informe de un ejercicio. SOLO LECTURA: nunca escribe en la base.

        Si existe un informe persistido lo devuelve; si no, lo calcula en
        memoria y lo marca con ``persisted=False`` y ``generated_at=None``
        (honesto: no esta guardado; un GET repetido no cambia el estado).
        La persistencia vive en ``regenerate_report`` (POST).
        """
        report = db.scalar(
            select(TaxReport).where(
                TaxReport.fiscal_year == fiscal_year
            ).order_by(TaxReport.updated_at.desc())
        )
        if report is not None:
            return {
                "summary": report.summary,
                "dividends": report.dividends,
                "realized": report.realized,
                "misc": report.misc,
                "generated_at": report.generated_at.isoformat() if report.generated_at else None,
                "persisted": True,
            }
        data = self.compute_report(db, fiscal_year)
        data["generated_at"] = None
        data["persisted"] = False
        return data

    def regenerate_report(self, db: Session, fiscal_year: int) -> dict:
        """Recalcula y PERSISTE el informe del ejercicio (camino POST)."""
        data = self.compute_report(db, fiscal_year)
        portfolio = self.fx.ensure_portfolio(db)
        report = db.scalar(
            select(TaxReport).where(TaxReport.fiscal_year == fiscal_year)
        )
        if report is None:
            report = TaxReport(
                portfolio_id=portfolio.id if portfolio else None,
                fiscal_year=fiscal_year,
                base_currency=data["summary"]["base_currency"],
            )
            db.add(report)
        report.base_currency = data["summary"]["base_currency"]
        report.summary = data["summary"]
        report.dividends = data["dividends"]
        report.realized = data["realized"]
        report.misc = data["misc"]
        report.generated_at = datetime.now(UTC)
        db.commit()
        db.refresh(report)
        data["generated_at"] = report.generated_at.isoformat()
        data["persisted"] = True
        return data



def build_tax_summary_rows(db: Session, fiscal_year: int | None = None) -> list[dict]:
    """Position-derived holdings summary used by the tax page.

    ``fiscal_year`` queda reservado para scoping por ano (ventas del ejercicio);
    las posiciones actuales no dependen del ano, asi que es opcional - la ruta
    ``GET /api/taxes/holdings`` lo llama sin ano.
    """
    rows = db.execute(
        select(Position, Company).join(Company, Position.company_id == Company.id)
    ).all()
    result = []
    for position, company in rows:
        result.append(
            {
                "ticker": company.ticker,
                "quantity": float(position.quantity),
                "cost_basis_base": float(position.cost_basis_base or 0),
                "unrealized_pnl_base": float(position.unrealized_pnl_base or 0),
                "as_of": position.as_of.isoformat(),
            }
        )
    return result