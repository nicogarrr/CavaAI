'use client';
import dynamic from 'next/dynamic';
import type { CompanyMarketSnapshot } from '@/lib/actions/market-workspace.actions';
const Chart = dynamic(() => import('./CompanyTechnicalChart'), { ssr: false, loading: () => <div className="h-[400px] animate-pulse rounded-xl border border-gray-800 bg-surface-1" role="status" aria-label="Cargando gráfico de precio" /> });
export function CompanyTechnicalWorkspace({ snapshot }: { snapshot: CompanyMarketSnapshot }) {
    return <Chart snapshot={snapshot} />;
}
