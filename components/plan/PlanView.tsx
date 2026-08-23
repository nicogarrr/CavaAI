'use client';

import { Landmark, PiggyBank, Target } from 'lucide-react';
import { RecordDetail, RecordList, type DataRecord } from '@/components/data/RecordViews';
import { getPlan, getPlanContributions, getPlanDrift } from '@/lib/actions/plan.actions';

interface PlanViewProps {
    initialPlan: DataRecord | null;
    initialContributions: DataRecord[];
    initialDrift: DataRecord | null;
}

export default function PlanView({ initialPlan, initialContributions, initialDrift }: PlanViewProps) {
    return (
        <div className="grid gap-6">
            <RecordDetail
                title="Plan de Inversión"
                description="Objetivo a largo plazo, aportación mensual y asignación objetivo"
                icon={<Target className="h-5 w-5 text-teal-400" />}
                record={initialPlan}
                fetchRecord={getPlan}
                maxKeys={20}
                emptyMessage="No hay plan de inversión configurado todavía."
            />

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