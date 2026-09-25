import { Check, Minus, X } from 'lucide-react';

import type { MoatScoreMetric } from '@/lib/actions/research.actions';
import { formatCompact, formatNumber, formatPercent } from '@/lib/format';

type MoatCheck = {
  check: string;
  metric: string;
  threshold: string | null;
  value: string | null;
  passed: boolean | null;
  reason?: string;
};

const CHECK_LABELS: Record<string, string> = {
  fcf_margin_5y_gt_5pct: 'Margen FCF 5 años',
  net_margin_5y_gt_15pct: 'Margen neto 5 años',
  roe_5y_gt_15pct: 'ROE 5 años',
  roa_5y_gt_7pct: 'ROA 5 años',
  roic_gt_wacc: 'ROIC',
  cfroi_approx_gt_wacc: 'CFROI (aprox.)',
  owner_earnings_5y_positive: 'Owner earnings 5 años',
  capex_to_da_5y_le_150pct: 'Capex / D&A 5 años',
};

const PERCENT_METRICS = new Set([
  'fcf_margin_5y',
  'net_margin_5y',
  'roe_5y',
  'roa_5y',
  'roic',
  'cfroi_approx',
  'wacc',
]);

function formatCheckValue(check: MoatCheck): string {
  if (check.value === null) return 'sin datos';
  if (PERCENT_METRICS.has(check.metric)) return formatPercent(check.value);
  if (check.metric === 'owner_earnings_5y') return formatCompact(check.value);
  return formatNumber(check.value, { maximumFractionDigits: 2 });
}

function formatThreshold(check: MoatCheck): string {
  if (check.check === 'roic_gt_wacc' || check.check === 'cfroi_approx_gt_wacc') {
    return check.threshold === null ? '> WACC' : `> WACC (${formatPercent(check.threshold)})`;
  }
  if (check.check === 'owner_earnings_5y_positive') return '> 0';
  if (check.check === 'capex_to_da_5y_le_150pct') {
    return `≤ ${formatNumber(check.threshold ?? '1.5', { maximumFractionDigits: 1 })}`;
  }
  return check.threshold === null ? '' : `> ${formatPercent(check.threshold)}`;
}

function CheckIcon({ passed }: { passed: boolean | null }) {
  if (passed === null) return <Minus aria-label="no evaluable" className="h-4 w-4 shrink-0 text-gray-500" />;
  if (passed) return <Check aria-label="superado" className="h-4 w-4 shrink-0 text-teal-300" />;
  return <X aria-label="no superado" className="h-4 w-4 shrink-0 text-rose-400" />;
}

/**
 * Panel del marco de calidad (MOAT V2): score + 8 checks trazables con
 * valor y umbral. Los checks sin datos quedan como no evaluables; nunca
 * cuentan como superados.
 */
export function MoatPanel({ metric }: { metric: MoatScoreMetric }) {
  const trace = metric.calculation_trace as {
    checks?: MoatCheck[];
    checks_evaluable?: number;
    checks_total?: number;
    score?: number;
  };
  const checks = trace.checks ?? [];
  const evaluable = trace.checks_evaluable ?? checks.filter((check) => check.passed !== null).length;
  const total = trace.checks_total ?? checks.length;
  const score = trace.score ?? checks.filter((check) => check.passed === true).length;

  if (metric.status === 'unavailable' || checks.length === 0) {
    return (
      <p className="text-sm leading-6 text-gray-400">
        Sin datos suficientes para evaluar el marco de calidad de esta empresa. Ningún check se
        da por superado sin datos.
      </p>
    );
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-baseline gap-2">
        <span className="text-2xl font-semibold text-gray-100">
          {score}/{total}
        </span>
        <span className="text-sm text-gray-400">
          checks superados
          {evaluable < total ? ` (${evaluable} de ${total} evaluables)` : ''}
        </span>
        {metric.status === 'partial' ? (
          <span className="rounded-full border border-amber-800 bg-amber-950/40 px-2 py-0.5 text-xs text-amber-300">
            parcial
          </span>
        ) : null}
      </div>
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {checks.map((check) => (
          <li
            className="flex min-w-0 items-center gap-3 rounded-lg border border-gray-800 bg-black/30 px-3 py-2.5"
            key={check.check}
          >
            <CheckIcon passed={check.passed} />
            <span className="min-w-0 flex-1 truncate text-sm text-gray-200">
              {CHECK_LABELS[check.check] ?? check.check}
            </span>
            <span className="shrink-0 text-right text-xs text-gray-400">
              <span className="block font-medium text-gray-300">{formatCheckValue(check)}</span>
              <span className="block">{formatThreshold(check)}</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs leading-5 text-gray-500">
        Marco V2 ({metric.definition_version}). Umbrales documentados en /metodologia. Los checks
        sin datos no cuentan como superados.
      </p>
    </div>
  );
}
