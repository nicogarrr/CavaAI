'use client';

import Link from 'next/link';
import { Crosshair, Landmark, PiggyBank, Target } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { RecordDetail, RecordList, type DataRecord } from '@/components/data/RecordViews';
import { getPlan, getPlanContributions, getPlanDrift } from '@/lib/actions/plan.actions';
import PlanSetupDialog from '@/components/plan/PlanSetupDialog';
import { t } from '@/lib/i18n/t';

interface PlanViewProps {
    initialPlan: DataRecord | null;
    initialContributions: DataRecord[];
    initialDrift: DataRecord | null;
}

/** Extrae tickers del drift (current_weights "ticker:XXX", deviations kind ticker) y del plan (targets kind ticker) */
function extractPlanTickers(drift: DataRecord | null, plan: DataRecord | null): string[] {
    const found = new Set<string>();

    const weights = drift?.current_weights;
    if (weights !== null && typeof weights === 'object' && !Array.isArray(weights)) {
        for (const key of Object.keys(weights)) {
            const match = /^ticker:(.+)$/i.exec(key);
            if (match) found.add(match[1].trim().toUpperCase());
        }
    }

    const collectTickerLabels = (items: unknown) => {
        if (!Array.isArray(items)) return;
        for (const item of items) {
            if (item === null || typeof item !== 'object' || Array.isArray(item)) continue;
            const record = item as DataRecord;
            if (record.kind === 'ticker' && typeof record.label === 'string' && record.label.trim()) {
                found.add(record.label.trim().toUpperCase());
            }
        }
    };
    collectTickerLabels(drift?.deviations);
    collectTickerLabels(drift?.suggestions);
    collectTickerLabels(plan?.target_allocations);

    return [...found].filter(Boolean).sort();
}

export default function PlanView({ initialPlan, initialContributions, initialDrift }: PlanViewProps) {
    const tickers = extractPlanTickers(initialDrift, initialPlan);

    return (
        <div className="grid gap-6">
            <RecordDetail
                title={t('plan.title')}
                description="Objetivo a largo plazo, aportación mensual y asignación objetivo"
                icon={<Target className="h-5 w-5 text-teal-400" />}
                record={initialPlan}
                fetchRecord={getPlan}
                maxKeys={20}
                emptyMessage={t('plan.empty')}
                emptyAction={<PlanSetupDialog />}
                actions={<PlanSetupDialog triggerLabel="Editar plan" initial={initialPlan} />}
            />

            <Card className="rounded-lg border border-gray-700 bg-gray-800/50">
                <CardHeader className="border-b border-gray-700/50 pb-4">
                    <div className="flex items-center gap-3">
                        <Crosshair className="h-5 w-5 text-teal-400" />
                        <div>
                            <CardTitle className="text-lg font-semibold text-gray-100">
                                Posiciones del plan
                            </CardTitle>
                            <CardDescription className="mt-0.5 text-sm text-gray-500">
                                Tickers con objetivo o peso actual: saltan a su ficha de research
                            </CardDescription>
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="pt-4">
                    {tickers.length === 0 ? (
                        <p className="py-6 text-center text-sm text-gray-500">
                            El plan no tiene posiciones por ticker todavía.
                        </p>
                    ) : (
                        <div className="flex flex-wrap gap-2">
                            {tickers.map((ticker) => (
                                <Link
                                    key={ticker}
                                    href={`/research/${encodeURIComponent(ticker)}`}
                                    className="rounded-lg border border-gray-700 px-3 py-1.5 font-mono text-sm font-semibold text-teal-300 transition hover:border-teal-700 hover:text-teal-200"
                                >
                                    {ticker}
                                </Link>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

            <RecordDetail
                title="Análisis de Drift"
                description="Desviación de la cartera actual frente a la asignación objetivo"
                icon={<PiggyBank className="h-5 w-5 text-teal-400" />}
                record={initialDrift}
                fetchRecord={getPlanDrift}
                maxKeys={24}
                emptyMessage="Sin análisis de drift disponible."
            />

            <RecordList
                title="Aportaciones"
                description="Historial de contribuciones al plan"
                icon={<Landmark className="h-5 w-5 text-teal-400" />}
                records={initialContributions}
                fetchRecords={getPlanContributions}
                columns={['date', 'amount', 'currency', 'note', 'external_id']}
                emptyMessage="Todavía no has registrado aportaciones a tu plan."
            />
        </div>
    );
}
