import { BarChart3, BrainCircuit, CheckCircle2, GitBranch } from 'lucide-react';
import { MutationForm } from '@/components/forms/MutationForm';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  createResearchDecision,
  reviewResearchExpectations,
  type ResearchDecisionJournalEntry,
  type ResearchExpectationReview,
  type ResearchLongTermModel,
} from '@/lib/actions/research.actions';

function compactNumber(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return 'N/A';
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);
}

function percentage(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? 'N/A' : `${(value * 100).toFixed(1)}%`;
}

function ModelStat({ label, value, positive = false }: { label: string; value: string; positive?: boolean }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-[#111111] p-4">
      <div className="text-xs font-semibold uppercase text-gray-500">{label}</div>
      <div className={`mt-2 text-2xl font-semibold ${positive ? 'text-teal-300' : 'text-gray-100'}`}>{value}</div>
    </div>
  );
}

export function LongTermModelPanel({ model }: { model: ResearchLongTermModel | null }) {
  if (!model) {
    return (
      <section className="rounded-lg border border-gray-800 bg-[#111111] p-5">
        <div className="flex items-center gap-2">
          <BrainCircuit className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Long-Term Fundamental Model</h2>
        </div>
        <p className="mt-3 text-sm text-gray-500">No se pudo construir el modelo con los datos disponibles.</p>
      </section>
    );
  }

  const base = model.scenarios.base;
  const year5 = base?.year_5 ?? base?.terminal_year;
  const terminal = base?.terminal_year;
  const growthAssumption = model.assumptions.revenue_growth;
  const marginAssumption = model.assumptions.fcf_margin;

  return (
    <section className="rounded-lg border border-gray-800 bg-[#111111] p-5">
      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center">
        <div className="flex items-center gap-2">
          <BrainCircuit className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Long-Term Fundamental Model</h2>
        </div>
        <span className="text-xs uppercase tracking-wide text-gray-500 md:ml-auto">
          {model.horizon_years}Y · {model.status} · coverage {model.source_coverage.coverage_percent.toFixed(0)}%
        </span>
      </div>

      {model.missing_inputs.length ? (
        <div className="mb-4 rounded-md border border-amber-900/70 bg-amber-950/20 p-3 text-sm text-amber-200">
          Modelo no publicable: faltan {model.missing_inputs.join(', ')}.
        </div>
      ) : null}

      <div className="mb-4 rounded-md border border-gray-800 bg-black/10 p-3 text-xs leading-5 text-gray-400">
        <span className="font-semibold text-gray-300">Drivers:</span> {model.framework.revenue_drivers.join(' · ')}
        <span className="mx-2 text-gray-700">|</span>
        <span className="font-semibold text-gray-300">KPIs:</span> {model.framework.kpis.join(' · ')}
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <ModelStat label={`${year5?.year ?? '5Y'} Revenue`} value={compactNumber(year5?.revenue)} />
        <ModelStat label={`${year5?.year ?? '5Y'} FCF`} value={compactNumber(year5?.free_cash_flow)} positive />
        <ModelStat label="FCF margin" value={percentage(year5?.fcf_margin)} />
        <ModelStat label="FCF / share" value={compactNumber(year5?.fcf_per_share)} positive />
      </div>

      <div className="mt-5 grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div>
          <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Bear / Base / Bull</div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs uppercase text-gray-500">
                <tr>
                  <th className="border-b border-gray-800 py-2">Scenario</th>
                  <th className="border-b border-gray-800 py-2 text-right">Revenue</th>
                  <th className="border-b border-gray-800 py-2 text-right">FCF</th>
                  <th className="border-b border-gray-800 py-2 text-right">FCF margin</th>
                  <th className="border-b border-gray-800 py-2 text-right">Value/share</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(model.scenarios).map(([name, scenario]) => {
                  const point = scenario.terminal_year;
                  return (
                    <tr key={name} className="border-b border-gray-900 last:border-0">
                      <td className="py-3 font-semibold capitalize text-gray-200">{name}</td>
                      <td className="py-3 text-right text-gray-300">{compactNumber(point?.revenue)}</td>
                      <td className="py-3 text-right text-gray-300">{compactNumber(point?.free_cash_flow)}</td>
                      <td className="py-3 text-right text-gray-300">{percentage(point?.fcf_margin)}</td>
                      <td className="py-3 text-right text-teal-200">{compactNumber(scenario.valuation?.value_per_share)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-3">
          <div className="rounded-md border border-gray-800 p-3">
            <div className="text-xs font-semibold uppercase text-gray-500">Base assumptions</div>
            <div className="mt-2 grid gap-2 text-sm">
              <div className="flex justify-between gap-3"><span className="text-gray-400">Revenue CAGR</span><span className="text-gray-200">{percentage(growthAssumption?.value)}</span></div>
              <div className="flex justify-between gap-3"><span className="text-gray-400">Normalized FCF margin</span><span className="text-gray-200">{percentage(marginAssumption?.value)}</span></div>
              <div className="flex justify-between gap-3"><span className="text-gray-400">ROIC / WACC</span><span className="text-gray-200">{percentage(terminal?.roic)} / {percentage(model.assumptions.wacc?.value)}</span></div>
            </div>
            <p className="mt-3 text-xs leading-5 text-gray-500">Sources revenue: {growthAssumption?.source_fact_ids.join(', ') || 'missing'} · FCF: {marginAssumption?.source_fact_ids.join(', ') || 'missing'}</p>
          </div>
          <div className="rounded-md border border-gray-800 p-3 text-sm">
            <div className="text-xs font-semibold uppercase text-gray-500">Reverse DCF</div>
            <p className="mt-2 text-gray-300">
              {model.reverse_dcf.status === 'ok'
                ? `El precio actual exige ${percentage(model.reverse_dcf.required_revenue_growth)} de crecimiento; la base asume ${percentage(model.reverse_dcf.base_revenue_growth)}.`
                : `No disponible: ${(model.reverse_dcf.missing_inputs ?? []).join(', ') || 'faltan inputs de mercado o financieros'}.`}
            </p>
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-6 xl:grid-cols-3">
        <div className="rounded-md border border-gray-800 p-3 text-sm">
          <div className="text-xs font-semibold uppercase text-gray-500">Quality of growth</div>
          <div className="mt-2 text-xl font-semibold capitalize text-gray-200">{model.quality_of_growth.quality}</div>
          <p className="mt-2 text-gray-400">Revenue CAGR {percentage(model.quality_of_growth.revenue_cagr.value)} · FCF margin change {percentage(model.quality_of_growth.fcf_margin_change.value)}</p>
          <p className="mt-2 text-xs leading-5 text-gray-500">{model.quality_of_growth.conclusion}</p>
        </div>
        <div className="rounded-md border border-gray-800 p-3 text-sm">
          <div className="text-xs font-semibold uppercase text-gray-500">Owner earnings</div>
          <div className="mt-2 text-xl font-semibold text-gray-200">{compactNumber(model.owner_earnings.value)}</div>
          <p className="mt-2 text-xs leading-5 text-gray-500">{model.owner_earnings.status === 'ok' ? model.owner_earnings.formula : `Insuficiente: ${(model.owner_earnings.missing_inputs ?? []).join(', ')}.`}</p>
        </div>
        <div className="rounded-md border border-gray-800 p-3 text-sm">
          <div className="text-xs font-semibold uppercase text-gray-500">Market Opportunity Engine</div>
          <div className="mt-2 text-sm font-semibold text-gray-200">{model.framework.label}</div>
          <p className="mt-2 text-gray-400">Top-down TAM {compactNumber(model.market_opportunity.top_down.tam.value)} · bottom-up {compactNumber(model.market_opportunity.bottom_up.value)}</p>
          <p className="mt-2 text-gray-400">Binding constraint: {model.market_opportunity.constraints.binding_constraint ?? 'unknown'}</p>
          <p className="mt-2 text-xs leading-5 text-gray-500">{model.market_opportunity.verdict.label} · {model.market_opportunity.verdict.conclusion}</p>
        </div>
      </div>

      <div className="mt-5 grid gap-6 xl:grid-cols-2">
        <div>
          <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500">What must be true</div>
          <ul className="space-y-2 text-sm">
            {model.what_must_be_true.slice(0, 6).map((item) => (
              <li key={item.id} className="flex gap-2 text-gray-300">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-teal-300" />
                <span>{item.condition}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Recent company timeline</div>
          <div className="space-y-2 text-sm">
            {model.timeline.slice(0, 4).map((event, index) => (
              <div key={`${event.date}-${event.title}-${index}`} className="rounded-md border border-gray-800 p-2">
                <div className="flex justify-between gap-3"><span className="font-medium text-gray-300">{event.title}</span><span className="text-xs text-gray-500">{event.date?.slice(0, 10) ?? 'unknown'}</span></div>
                <div className="mt-1 text-xs text-gray-500">{event.type} · {event.source} · impact {event.thesis_impact}</div>
              </div>
            ))}
            {!model.timeline.length ? <div className="text-sm text-gray-500">No hay eventos históricos almacenados.</div> : null}
          </div>
        </div>
      </div>

      <p className="mt-5 border-t border-gray-800 pt-3 text-xs leading-5 text-gray-500">
        El modelo cubre {model.historical_review.years_covered} años ({model.historical_review.first_year ?? '—'}–{model.historical_review.last_year ?? '—'}). Los números calculados conservan sus fact IDs; lo no disponible se muestra como unknown/insufficient_data.
      </p>
    </section>
  );
}

export function DecisionAndRealityPanel({
  ticker,
  decisions,
  reviews,
}: {
  ticker: string;
  decisions: ResearchDecisionJournalEntry[];
  reviews: ResearchExpectationReview[];
}) {
  return (
    <section className="grid gap-6 xl:grid-cols-2">
      <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
        <div className="mb-4 flex items-center gap-2">
          <GitBranch className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Decision Journal</h2>
        </div>
        <MutationForm
          action={createResearchDecision.bind(null, ticker)}
          className="grid gap-3"
          resetOnSuccess
          successMessage="Decisión registrada contra la tesis vigente"
        >
          <select aria-label="Decision" className="h-10 rounded-md border border-gray-700 bg-gray-900 px-3 text-sm text-gray-200" defaultValue="hold" name="decision">
            <option value="buy">Buy</option>
            <option value="hold">Hold</option>
            <option value="trim">Trim</option>
            <option value="sell">Sell</option>
            <option value="watch">Watch</option>
            <option value="avoid">Avoid</option>
          </select>
          <Textarea aria-label="Decision rationale" className="border-gray-700 bg-transparent text-gray-100" name="rationale" placeholder="Qué evidencia justifica esta decisión" required />
          <Textarea aria-label="What must be true" className="border-gray-700 bg-transparent text-gray-100" name="what_must_be_true" placeholder="Una condición verificable por línea" />
          <Button type="submit">Registrar decisión</Button>
        </MutationForm>
        <div className="mt-5 space-y-3">
          {decisions.length === 0 ? (
            <p className="text-sm text-gray-500">Todavía no hay decisiones registradas.</p>
          ) : decisions.slice(0, 8).map((entry) => (
            <div className="rounded-md border border-gray-800 p-3" key={entry.id}>
              <div className="flex items-center justify-between gap-3">
                <Badge variant="outline">{entry.decision}</Badge>
                <span className="text-xs text-gray-500">{entry.decision_date}</span>
              </div>
              <p className="mt-2 text-sm text-gray-300">{entry.rationale}</p>
              <p className="mt-2 text-xs text-gray-500">Thesis {entry.thesis_version_id ?? '—'} · Model {entry.model_version_id ?? '—'}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
        <div className="mb-4 flex items-center gap-2">
          <BarChart3 className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Expectation vs Reality</h2>
          <MutationForm action={reviewResearchExpectations.bind(null, ticker)} className="ml-auto" successMessage="Forecasts comparados con los hechos disponibles">
            <Button size="sm" type="submit" variant="outline">Comparar ahora</Button>
          </MutationForm>
        </div>
        {reviews.length === 0 ? (
          <p className="text-sm text-gray-500">Ejecuta la comparación cuando existan forecasts persistidos.</p>
        ) : (
          <div className="max-h-[560px] overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-gray-500">
                <tr>
                  <th className="border-b border-gray-800 py-2">Año / KPI</th>
                  <th className="border-b border-gray-800 py-2 text-right">Esperado</th>
                  <th className="border-b border-gray-800 py-2 text-right">Real</th>
                  <th className="border-b border-gray-800 py-2 text-right">Estado</th>
                </tr>
              </thead>
              <tbody>
                {reviews.slice(0, 40).map((review) => (
                  <tr className="border-b border-gray-900" key={review.id}>
                    <td className="py-3 text-gray-300">{review.fiscal_year} · {review.metric}</td>
                    <td className="py-3 text-right text-gray-400">{compactNumber(review.expected_value)}</td>
                    <td className="py-3 text-right text-gray-400">{compactNumber(review.actual_value)}</td>
                    <td className="py-3 text-right"><Badge variant="outline">{review.status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
