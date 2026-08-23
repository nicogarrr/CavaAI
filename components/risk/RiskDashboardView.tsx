'use client';

import { Gauge } from 'lucide-react';
import { RecordDetail, type DataRecord } from '@/components/data/RecordViews';
import { getRiskDashboard } from '@/lib/actions/risk.actions';

interface RiskDashboardViewProps {
    initialDashboard: DataRecord | null;
}

export default function RiskDashboardView({ initialDashboard }: RiskDashboardViewProps) {
    return (
        <RecordDetail
            title="Dashboard de Riesgo"
            description="Métricas agregadas de riesgo: volatilidad, drawdown, VaR, correlaciones y exposición"
            icon={<Gauge className="h-5 w-5 text-teal-400" />}
            record={initialDashboard}
            fetchRecord={getRiskDashboard}
            maxKeys={32}
            emptyMessage="No hay métricas de riesgo disponibles. Comprueba que tu cartera tiene posiciones."
        />
    );
}