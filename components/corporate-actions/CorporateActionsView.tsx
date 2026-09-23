'use client';

import { useState } from 'react';
import { Building2, CheckCircle2, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { RecordList, researchHrefFor, type DataRecord } from '@/components/data/RecordViews';
import { applyCorporateAction, getCorporateActions } from '@/lib/actions/corporate-actions.actions';
import { showErrorToast } from '@/lib/toast';
import { toast } from 'sonner';

interface CorporateActionsViewProps {
    initialActions: DataRecord[];
}

function recordActionId(record: DataRecord): number {
    const value = record.id ?? record.action_id;
    const parsed = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(parsed) ? parsed : NaN;
}

function isApplied(record: DataRecord): boolean {
    return record.applied === true
        || record.status === 'applied'
        || record.applied_at !== undefined && record.applied_at !== null;
}

export default function CorporateActionsView({ initialActions }: CorporateActionsViewProps) {
    const [applyingId, setApplyingId] = useState<number | null>(null);

    const handleApply = async (record: DataRecord) => {
        const actionId = recordActionId(record);
        if (!Number.isFinite(actionId)) {
            toast.error('La acción corporativa no tiene un identificador válido');
            return;
        }
        setApplyingId(actionId);
        try {
            await applyCorporateAction(actionId);
            toast.success('Acción corporativa aplicada a la cartera');
        } catch (error) {
            showErrorToast(error);
        } finally {
            setApplyingId(null);
        }
    };

    return (
        <RecordList
            title="Acciones Corporativas"
            description="Dividendos, splits, spin-offs y fusiones pendientes de aplicar a la cartera"
            icon={<Building2 className="h-5 w-5 text-teal-400" />}
            records={initialActions}
            fetchRecords={getCorporateActions}
            columns={['ticker', 'action_type', 'description', 'effective_date', 'ratio', 'status']}
            emptyMessage="No hay acciones corporativas pendientes. ¡Todo al día!"
            linkColumns={{ ticker: (record) => researchHrefFor(record) }}
            rowActions={(record) => {
                const actionId = recordActionId(record);
                if (isApplied(record)) {
                    return (
                        <span className="inline-flex items-center gap-1.5 text-xs text-gray-500">
                            <CheckCircle2 className="h-4 w-4 text-teal-400" />
                            Aplicada
                        </span>
                    );
                }
                return (
                    <Button
                        size="sm"
                        variant="outline"
                        disabled={!Number.isFinite(actionId) || applyingId === actionId}
                        onClick={() => handleApply(record)}
                        className="gap-1.5 border-teal-800 text-teal-300 hover:bg-teal-900/20 hover:text-teal-200"
                    >
                        {applyingId === actionId ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                            <CheckCircle2 className="h-3.5 w-3.5" />
                        )}
                        Aplicar
                    </Button>
                );
            }}
        />
    );
}