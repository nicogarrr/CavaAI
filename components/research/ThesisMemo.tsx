import { formatMoney, formatPercent, formatUserDate, NA } from '@/lib/format';
import { GlossaryTerm } from '@/components/GlossaryTerm';
import ScenarioAssumptions from '@/components/research/ScenarioAssumptions';
import ThesisDebatePanel from '@/components/research/ThesisDebatePanel';
import { Badge } from '@/components/ui/badge';
import type { ResearchThesis } from '@/lib/actions/research.actions';
import type { GlossaryKey } from '@/lib/glossary';

function money(value: number | string | null | undefined): string {
  const parsed = typeof value === 'string' ? Number(value) : value;
  if (parsed === null || parsed === undefined || Number.isNaN(parsed)) return NA;
  return formatMoney(parsed, 'USD', { maximumFractionDigits: 2 });
}

function pct(value: number | string | null | undefined): string {
  const parsed = typeof value === 'string' ? Number(value) : value;
  if (parsed === null || parsed === undefined || Number.isNaN(parsed)) return NA;
  return formatPercent(parsed);
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  const tone =
    clamped >= 70 ? 'bg-teal-400' : clamped >= 40 ? 'bg-amber-400' : 'bg-red-400';
  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="truncate text-gray-400">{label}</span>
        <span className="font-mono text-gray-300">{clamped}/100</span>
      </div>
      <div className="mt-1 h-1.5 w-full rounded-full bg-gray-800">
        <div className={`h-1.5 rounded-full ${tone}`} style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}

function ScenarioCell({
  label,
  value,
  probability,
  highlight = false,
  glossaryKey,
}: {
  label: string;
  value: number | string | null | undefined;
  probability?: number | null;
  highlight?: boolean;
  glossaryKey?: GlossaryKey;
}) {
  return (
    <div
      className={`rounded-lg border p-3 ${
        highlight ? 'border-teal-800 bg-teal-950/20' : 'border-gray-800 bg-black/20'
      }`}
    >
      <div className="text-xs uppercase text-gray-500">
        {glossaryKey ? (
          <GlossaryTerm k={glossaryKey} icon={false}>
            {label}
          </GlossaryTerm>
        ) : (
          label
        )}
      </div>
      <div className="mt-1 text-base font-semibold text-gray-100">{money(value)}</div>
      {probability !== null && probability !== undefined ? (
        <div className="mt-0.5 text-xs text-gray-500">p = {formatPercent(probability, { digits: 0 })}</div>
      ) : null}
    </div>
  );
}

/**
 * Layout estructurado de la tesis: hipotesis, escenarios con probabilidades,
 * scores de calidad, catalizadores con fecha y criterios de invalidacion,
 * seguidos del memorando completo en markdown. Mobile-first: los escenarios
 * apilan en 2 columnas y el resto en 1.
 *
 * Las versiones anteriores a los campos profesionales (hypothesis=null)
 * muestran estados honestos "pendiente", nunca datos inventados.
 */
export default function ThesisMemo({
  thesis,
  ticker,
  debateBody,
}: {
  thesis: ResearchThesis;
  /** Ticker para el debate bull/bear (bloque interactivo de abajo). */
  ticker?: string;
  /** Cuerpo persistido de la seccion thesis_debate (veredicto previo). */
  debateBody?: string | null;
}) {
  const probabilities = thesis.scenario_probabilities ?? {};
  const generatedAt = new Date(thesis.created_at);
  const generatedLabel = formatUserDate(generatedAt, { day: 'numeric', month: 'short', year: 'numeric' }, undefined) || null;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge>{thesis.rating}</Badge>
        <Badge variant="outline">{thesis.status}</Badge>
        <Badge variant="outline">v{thesis.version}</Badge>
        {generatedLabel ? (
          <span className="text-xs text-gray-500">generada el {generatedLabel}</span>
        ) : null}
        {thesis.stale ? (
          <span className="rounded-full border border-amber-800/60 bg-amber-950/40 px-2.5 py-0.5 text-xs font-medium text-amber-300">
            Datos nuevos disponibles — considera regenerar
          </span>
        ) : null}
      </div>

      <p className="text-sm leading-6 text-gray-300">{thesis.executive_summary}</p>

      <section className="rounded-lg border border-teal-900/60 bg-teal-950/10 p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-teal-300">Hipótesis</h3>
        <p className="mt-2 text-sm leading-6 text-gray-200">
          {thesis.hypothesis ??
            'Pendiente: esta versión es anterior a los campos profesionales. Genera una nueva versión para registrar la hipótesis.'}
        </p>
      </section>

      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
          Escenarios y valoración
        </h3>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
          <ScenarioCell label="Precio" value={thesis.current_price} />
          <ScenarioCell label="Bear" value={thesis.bear_value} probability={probabilities['bear']} glossaryKey="bear" />
          <ScenarioCell label="Base" value={thesis.base_value} probability={probabilities['base']} highlight glossaryKey="base" />
          <ScenarioCell label="Bull" value={thesis.bull_value} probability={probabilities['bull']} glossaryKey="bull" />
          <ScenarioCell label="Valor esperado" value={thesis.expected_value} />
          <div className="rounded-lg border border-gray-800 bg-black/20 p-3">
            <div className="text-xs uppercase text-gray-500">
              <GlossaryTerm k="margen_seguridad" icon={false}>
                Margen seguridad
              </GlossaryTerm>
            </div>
            <div className="mt-1 text-base font-semibold text-gray-100">
              {pct(thesis.margin_of_safety)}
            </div>
          </div>
        </div>
        <ScenarioAssumptions />
      </section>

      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
          Calidad de la evidencia
        </h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <ScoreBar label="Confianza en datos" value={thesis.data_confidence_score} />
          <ScoreBar label="Cobertura de fuentes" value={thesis.source_coverage_score} />
          <ScoreBar label="Red team" value={thesis.red_team_score} />
          <ScoreBar label="Riesgo de valoración" value={thesis.valuation_risk_score} />
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-gray-800 p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400">
            Catalizadores
          </h3>
          {thesis.catalysts && thesis.catalysts.length > 0 ? (
            <ul className="mt-2 space-y-2 text-sm text-gray-300">
              {thesis.catalysts.map((catalyst, index) => (
                <li key={index} className="flex flex-wrap items-baseline gap-x-2">
                  <span className="font-medium text-gray-200">{catalyst.label ?? 'Catalizador'}</span>
                  {catalyst.date ? (
                    <span className="text-gray-400">
                      · {catalyst.date}
                      {catalyst.time ? ` ${catalyst.time}` : ''}
                    </span>
                  ) : null}
                  {catalyst.eps_forecast !== undefined ? (
                    <span className="text-gray-500">· EPS est. {catalyst.eps_forecast}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-gray-500">
              Sin catalizadores con fecha conocida; pendiente del calendario de resultados.
            </p>
          )}
        </section>

        <section className="rounded-lg border border-red-900/50 bg-red-950/10 p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-red-300">
            Qué invalidaría la tesis
          </h3>
          {thesis.invalidation_criteria && thesis.invalidation_criteria.length > 0 ? (
            <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-6 text-gray-300">
              {thesis.invalidation_criteria.map((criterion, index) => (
                <li key={index}>{criterion}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-gray-500">
              Pendiente: genera una nueva versión para registrar criterios de invalidación.
            </p>
          )}
        </section>
      </div>

      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
          Debate bull/bear
        </h3>
        {ticker ? (
          <ThesisDebatePanel ticker={ticker} initialVerdict={debateBody ?? null} />
        ) : (
          <p className="text-sm text-gray-500">
            Debate no disponible sin ticker: recarga la ficha para contrastar la tesis.
          </p>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
          Memorando completo
        </h3>
        <div className="whitespace-pre-wrap rounded-lg border border-gray-800 bg-black/20 p-4 text-sm leading-6 text-gray-400">
          {thesis.thesis_markdown}
        </div>
      </section>
    </div>
  );
}
