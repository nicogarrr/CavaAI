import type {
  InvestorDatum,
  InvestorPortfolio,
} from "@/lib/actions/investors.actions";
import { formatMarketCapUsd, formatNumber, formatPercent } from "@/lib/format";
import { Pagination, paginate } from "./Pagination";
import { periodLabel } from "./format";

const ACTIONS: Record<string, string> = {
  compra: "Compra",
  venta: "Venta",
  nueva: "Nueva",
  cerrada: "Cerrada",
  aumento: "Aumento",
  reduccion: "Reducción",
  donacion: "Donación",
  alta: "Alta",
  otro: "Otro",
  sin_datos: "SIN_DATOS",
  concesion: "Concesión",
  ejercicio: "Ejercicio",
  retencion: "Retención",
};

export function Datum({
  datum,
  kind = "number",
}: {
  datum: InvestorDatum;
  kind?: "number" | "usd" | "percent";
}) {
  // Fail closed even if a malformed payload claims OFICIAL without a dated source.
  const available =
    datum.value !== null &&
    Number.isFinite(datum.value) &&
    datum.label !== "SIN_DATOS" &&
    datum.as_of &&
    (datum.label !== "OFICIAL" || datum.source_url);
  const text = !available
    ? "SIN_DATOS"
    : kind === "usd"
      ? formatMarketCapUsd(datum.value)
      : kind === "percent"
        ? formatPercent(datum.value, { fromRatio: false })
        : formatNumber(datum.value);
  return (
    <span className="flex flex-col gap-1">
      <span className="font-medium text-gray-100">{text}</span>
      {available ? (
        <span
          className={`text-xs ${datum.label === "INFERIDO" ? "text-amber-300" : "text-gray-500"}`}
        >
          {datum.label} · {periodLabel(datum.as_of)}
          {datum.source_url ? (
            <>
              {" "}
              ·{" "}
              <a
                className="hover:underline"
                href={datum.source_url}
                rel="noreferrer"
                target="_blank"
              >
                Fuente
              </a>
            </>
          ) : null}
        </span>
      ) : null}
    </span>
  );
}

export function Portfolio({
  portfolio,
  view,
  pagina,
}: {
  portfolio: InvestorPortfolio;
  view: string;
  pagina?: string;
}) {
  const positions = paginate(portfolio.positions, pagina, 20);
  const movements = paginate(portfolio.movements, pagina, 20);
  const paged = view === "cambios" ? movements : positions;
  return (
    <section aria-label="Cartera declarada" className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <Datum datum={portfolio.total_value_usd} kind="usd" />
        <span className="text-sm text-gray-500">
          {portfolio.positions.length}{" "}
          {portfolio.positions.length === 1
            ? "posición documentada"
            : "posiciones documentadas"}
          {portfolio.as_of ? ` · ${periodLabel(portfolio.as_of)}` : ""}
        </span>
      </div>
      {portfolio.coverage === "partial" ? (
        <p role="status" className="text-sm text-amber-300">
          Datos parciales
        </p>
      ) : null}
      {paged.items.length === 0 ? (
        <p className="text-sm text-gray-500">
          SIN_DATOS{view === "cambios" ? " · Sin movimientos documentados" : ""}
        </p>
      ) : view === "cambios" ? (
        <ul className="divide-y divide-gray-800">
          {movements.items.map((row, index) => (
            <li
              className="flex flex-col gap-3 py-4"
              key={`${row.issuer}-${row.date}-${index}`}
            >
              <div className="flex flex-wrap justify-between gap-2">
                <h3 className="text-sm text-gray-100">{row.issuer}</h3>
                <span className="text-sm text-gray-400">
                  {ACTIONS[row.action] ?? "Otro"} · {periodLabel(row.date)}
                </span>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <div>
                  <p className="mb-1 text-xs text-gray-500">
                    Acciones · variación
                  </p>
                  <Datum datum={row.shares} />
                </div>
                <div>
                  <p className="mb-1 text-xs text-gray-500">Acciones después</p>
                  <Datum datum={row.shares_after} />
                </div>
                <div>
                  <p className="mb-1 text-xs text-gray-500">Precio</p>
                  <Datum datum={row.price_usd} kind="usd" />
                </div>
              </div>
              {row.note ? (
                <p className="text-xs text-gray-500">{row.note}</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <ul className="divide-y divide-gray-800">
          {positions.items.map((row, index) => (
            <li
              className="flex flex-col gap-3 py-4"
              key={`${row.cusip}-${row.title_of_class}-${index}`}
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-sm font-medium text-gray-100">
                  {row.issuer}
                  {row.ticker ? ` · ${row.ticker}` : ""}
                </h3>
                <span className="text-xs text-gray-500">
                  {row.source_form} · {row.title_of_class}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div>
                  <p className="mb-1 text-xs text-gray-500">Valor</p>
                  <Datum datum={row.value_usd} kind="usd" />
                </div>
                <div>
                  <p className="mb-1 text-xs text-gray-500">Peso en cartera</p>
                  <Datum datum={row.weight_pct} kind="percent" />
                </div>
                <div>
                  <p className="mb-1 text-xs text-gray-500">Acciones</p>
                  <Datum datum={row.shares} />
                </div>
                <div>
                  <p className="mb-1 text-xs text-gray-500">
                    Participación en emisor
                  </p>
                  <Datum datum={row.ownership_pct} kind="percent" />
                </div>
              </div>
              {view === "distribucion" &&
              row.weight_pct.value !== null &&
              Number.isFinite(row.weight_pct.value) &&
              row.weight_pct.label !== "SIN_DATOS" ? (
                <div
                  aria-hidden="true"
                  className="h-1.5 overflow-hidden rounded-full bg-gray-900"
                >
                  <div
                    className="h-full rounded-full bg-lime-300/70"
                    style={{
                      width: `${Math.min(100, Math.max(0, row.weight_pct.value))}%`,
                    }}
                  />
                </div>
              ) : null}
              {row.note ? (
                <p className="text-xs text-gray-500">{row.note}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      <Pagination
        basePath={`/inversores/${portfolio.slug}`}
        page={paged.page}
        total={paged.total}
        params={{ vista: view }}
      />
      <p className="text-xs text-gray-500">{portfolio.limitations}</p>
    </section>
  );
}
