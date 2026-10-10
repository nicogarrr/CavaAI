import type { PortfolioForecast } from '@/lib/actions/portfolio.actions';
import { Panel } from '@/components/ui/panel';

const SCENARIO_LABELS: Record<string, string> = {
  bear: 'Oso',
  base: 'Base',
  bull: 'Toro',
};

function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return 'Sin datos';
  return `${(value * 100).toFixed(digits)}%`;
}

function signedPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return 'Sin datos';
  const rendered = (value * 100).toFixed(digits);
  return value > 0 ? `+${rendered}%` : `${rendered}%`;
}

/**
 * Prevision de rentabilidad a ~5 anos desde el valor intrinseco.
 * Toda cifra viene del endpoint determinista /api/portfolio/forecast:
 * los precios son OFICIALES (fuente + fecha por posicion) y los valores
 * intrinsecos INFERIDOS (tesis/modelo vigente, version visible). Lo que
 * no tiene tesis se lista aparte con su peso; nunca se inventa un cero.
 */
export default function PortfolioForecast({ forecast }: { forecast: PortfolioForecast }) {
  const portfolio = forecast.portfolio;
  if (!portfolio) {
    return (
      <Panel title="Prevision a 5 anos">
        <p className="text-sm text-gray-400">Sin posiciones: no hay prevision que calcular.</p>
      </Panel>
    );
  }
  const scenarioOrder = ['bear', 'base', 'bull'] as const;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {scenarioOrder.map((key) => {
          const scenario = portfolio.scenarios?.[key];
          return (
            <div className="rounded-lg border border-gray-800 p-4" key={key}>
              <p className="text-xs uppercase tracking-wide text-gray-500">{SCENARIO_LABELS[key]}</p>
              <p className="mt-1 text-2xl font-semibold text-gray-100">
                {scenario ? signedPct(scenario.contribution_cagr) : 'Sin datos'}
              </p>
              <p className="mt-1 text-xs text-gray-500">
                Contribucion anual · aporte total {scenario ? signedPct(scenario.contribution_total_return) : 'Sin datos'}
                {scenario?.horizon_scope === 'mixed' ? ' · horizontes mezclados (proxy anual)' : ''}
              </p>
            </div>
          );
        })}
        <div className="rounded-lg border border-teal-900/60 bg-teal-950/20 p-4">
          <p className="text-xs uppercase tracking-wide text-teal-300">Esperado ponderado</p>
          <p className="mt-1 text-2xl font-semibold text-teal-100">
            {signedPct(portfolio.expected_cagr)}
          </p>
          <p className="mt-1 text-xs text-gray-500">
            {portfolio.expected_cagr !== null
              ? 'Probabilidades propias de cada tesis, ponderadas por tu peso real.'
              : 'Solo se emite con cobertura completa de la cartera valorada; abajo van las contribuciones por posicion.'}
          </p>
        </div>
      </div>
      <Panel
        title="Por posicion"
        description={`Cobertura: ${portfolio.covered_weight !== null ? pct(portfolio.covered_weight) : 'Sin datos (hay posiciones sin conversion; pesos sobre el subset valorado)'} de la cartera con tesis computable (${portfolio.covered_count} de ${portfolio.position_count} posiciones). Precios OFICIALES con fuente y fecha; valores intrinsecos INFERIDOS del modelo vigente.`}
      >
        <div className="overflow-x-auto" role="region" aria-label="Prevision por posicion" tabIndex={0}>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-xs uppercase tracking-wide text-gray-500">
                <th className="py-2 pr-4">Posicion</th>
                <th className="py-2 pr-4">Peso</th>
                <th className="py-2 pr-4">Oso</th>
                <th className="py-2 pr-4">Base</th>
                <th className="py-2 pr-4">Toro</th>
                <th className="py-2 pr-4">Esperado</th>
                <th className="py-2">Base del calculo</th>
              </tr>
            </thead>
            <tbody>
              {forecast.positions.map((item) => (
                <tr className="border-b border-gray-900 text-gray-300" key={item.ticker}>
                  <td className="py-2 pr-4 font-medium text-gray-100">{item.ticker}</td>
                  <td className="py-2 pr-4">
                    {pct(item.weight)}
                    {item.weight_scope === 'valued_subset' ? (
                      <span className="block text-xs text-amber-400/80">sobre subset valorado</span>
                    ) : null}
                  </td>
                  <td className="py-2 pr-4">{signedPct(item.cagr.bear)}</td>
                  <td className="py-2 pr-4">{signedPct(item.cagr.base)}</td>
                  <td className="py-2 pr-4">{signedPct(item.cagr.bull)}</td>
                  <td className="py-2 pr-4">
                    {item.expected_cagr !== null
                      ? signedPct(item.expected_cagr)
                      : item.partial_expected_cagr !== null
                        ? `Parcial ${signedPct(item.partial_expected_cagr)}`
                        : 'Sin datos'}
                  </td>
                  <td className="py-2 text-xs text-gray-500">
                    Precio {item.price_source} · {item.price_as_of} · tesis v{item.thesis_version} ({item.thesis_status})
                    {item.model_version !== null ? ` · modelo v${item.model_version}` : ''} · {item.horizon_years} anos
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {forecast.excluded.length > 0 ? (
          <div className="mt-4 rounded-lg border border-amber-900/70 bg-amber-950/20 p-3">
            <p className="text-sm font-medium text-amber-200">Fuera de la prevision (sin tesis computable):</p>
            <ul className="mt-1 space-y-1 text-sm text-amber-100/80">
              {forecast.excluded.map((item) => (
                <li key={item.ticker}>
                  {item.ticker} — {pct(item.weight)} de la cartera. {item.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </Panel>
      <Panel title="Supuestos" density="compact">
        <ul className="list-disc space-y-1 pl-5 text-xs leading-5 text-gray-500">
          {forecast.assumptions.map((assumption) => (
            <li key={assumption}>{assumption}</li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
