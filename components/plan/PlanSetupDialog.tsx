'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, Target, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { upsertPlan, type PlanTargetInput } from '@/lib/actions/plan.actions';
import { showErrorToast } from '@/lib/toast';
import { toast } from 'sonner';

type AllocationRow = { label: string; target_pct: string };

/**
 * Alta/edición del plan de inversión (B12): el backend tenía PUT /api/plan
 * pero la UI no ofrecía ninguna vía para crear el plan.
 */
type PlanInitial = {
    monthly_contribution?: unknown;
    start_date?: unknown;
    horizon_years?: unknown;
    target_allocations?: unknown;
};

function asText(value: unknown): string {
    return typeof value === 'number' || typeof value === 'string' ? String(value) : '';
}

export default function PlanSetupDialog({
    triggerLabel = 'Configurar plan',
    initial,
}: {
    triggerLabel?: string;
    /** Plan existente para precargar el formulario (edición). */
    initial?: PlanInitial | null;
}) {
    const router = useRouter();
    const [open, setOpen] = useState(false);
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [monthly, setMonthly] = useState(() => asText(initial?.monthly_contribution));
    const [startDate, setStartDate] = useState(
        () => asText(initial?.start_date) || new Date().toISOString().split('T')[0],
    );
    const [horizon, setHorizon] = useState(() => asText(initial?.horizon_years) || '30');
    const [rows, setRows] = useState<AllocationRow[]>(() => {
        const allocations = Array.isArray(initial?.target_allocations)
            ? (initial?.target_allocations as Record<string, unknown>[])
            : [];
        const parsed = allocations
            .filter((a) => a && typeof a === 'object')
            .map((a) => ({ label: asText(a.label), target_pct: asText(a.target_pct) }))
            .filter((a) => a.label);
        return parsed.length ? parsed : [{ label: '', target_pct: '' }];
    });

    const addRow = () => setRows((prev) => [...prev, { label: '', target_pct: '' }]);
    const removeRow = (index: number) => setRows((prev) => prev.filter((_, i) => i !== index));
    const updateRow = (index: number, patch: Partial<AllocationRow>) =>
        setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));

    const handleSubmit = async (event: React.FormEvent) => {
        event.preventDefault();
        setError(null);

        const monthlyContribution = Number(monthly.replace(',', '.'));
        if (!Number.isFinite(monthlyContribution) || monthlyContribution <= 0) {
            setError('La aportación mensual debe ser un número mayor que 0.');
            return;
        }
        const horizonYears = Number.parseInt(horizon, 10);
        if (!Number.isInteger(horizonYears) || horizonYears < 1 || horizonYears > 80) {
            setError('El horizonte debe ser un entero entre 1 y 80 años.');
            return;
        }
        const allocations: PlanTargetInput[] = [];
        let totalPct = 0;
        for (const row of rows) {
            const label = row.label.trim().toUpperCase();
            if (!label && !row.target_pct.trim()) continue;
            const pct = Number(row.target_pct.replace(',', '.'));
            if (!label || !Number.isFinite(pct) || pct <= 0 || pct > 100) {
                setError('Cada asignación necesita un ticker y un porcentaje entre 0 y 100.');
                return;
            }
            totalPct += pct;
            allocations.push({ kind: 'ticker', label, target_pct: pct, band_pct: 5 });
        }
        if (totalPct > 100) {
            setError(`Las asignaciones suman ${totalPct}%: no pueden superar el 100%.`);
            return;
        }

        setPending(true);
        try {
            await upsertPlan({
                monthly_contribution: monthlyContribution,
                start_date: startDate,
                horizon_years: horizonYears,
                target_allocations: allocations,
            });
            toast.success('Plan de inversión guardado');
            setOpen(false);
            router.refresh();
        } catch (exc) {
            showErrorToast(exc, { onRetry: () => handleSubmitRetry() });
        } finally {
            setPending(false);
        }
    };

    // Reintento desde el toast (motor caído): reenvía el último submit válido.
    const handleSubmitRetry = async () => {
        const form = document.getElementById('plan-setup-form') as HTMLFormElement | null;
        form?.requestSubmit();
    };

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button type="button" className="gap-2">
                    <Target className="h-4 w-4" />
                    {triggerLabel}
                </Button>
            </DialogTrigger>
            <DialogContent className="border-gray-700 bg-gray-900 text-gray-100 sm:max-w-lg">
                <DialogHeader>
                    <DialogTitle>Configurar plan de inversión</DialogTitle>
                    <DialogDescription className="text-gray-400">
                        Aportación mensual, horizonte y asignación objetivo por ticker. La suma de
                        porcentajes no puede superar el 100%.
                    </DialogDescription>
                </DialogHeader>
                <form id="plan-setup-form" onSubmit={handleSubmit} className="space-y-4">
                    <div className="grid gap-4 sm:grid-cols-3">
                        <div className="space-y-1.5">
                            <Label htmlFor="plan-monthly" className="text-gray-300">Aportación mensual (€)</Label>
                            <Input
                                id="plan-monthly"
                                inputMode="decimal"
                                value={monthly}
                                onChange={(e) => setMonthly(e.target.value)}
                                placeholder="300"
                                className="border-gray-700 bg-gray-800 text-gray-100"
                                required
                            />
                        </div>
                        <div className="space-y-1.5">
                            <Label htmlFor="plan-start" className="text-gray-300">Inicio</Label>
                            <Input
                                id="plan-start"
                                type="date"
                                value={startDate}
                                onChange={(e) => setStartDate(e.target.value)}
                                className="border-gray-700 bg-gray-800 text-gray-100"
                                required
                            />
                        </div>
                        <div className="space-y-1.5">
                            <Label htmlFor="plan-horizon" className="text-gray-300">Horizonte (años)</Label>
                            <Input
                                id="plan-horizon"
                                inputMode="numeric"
                                value={horizon}
                                onChange={(e) => setHorizon(e.target.value)}
                                className="border-gray-700 bg-gray-800 text-gray-100"
                                required
                            />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <p className="text-sm font-medium text-gray-300">Asignación objetivo por ticker</p>
                        {rows.map((row, index) => (
                            <div key={index} className="flex items-center gap-2">
                                <Input
                                    aria-label={`Ticker ${index + 1}`}
                                    value={row.label}
                                    onChange={(e) => updateRow(index, { label: e.target.value })}
                                    placeholder="SAN.MC"
                                    className="border-gray-700 bg-gray-800 text-gray-100"
                                />
                                <Input
                                    aria-label={`Porcentaje objetivo ${index + 1}`}
                                    inputMode="decimal"
                                    value={row.target_pct}
                                    onChange={(e) => updateRow(index, { target_pct: e.target.value })}
                                    placeholder="%"
                                    className="w-24 border-gray-700 bg-gray-800 text-gray-100"
                                />
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => removeRow(index)}
                                    disabled={rows.length === 1}
                                    aria-label="Quitar fila"
                                    className="text-gray-400 hover:text-red-400"
                                >
                                    <Trash2 className="h-4 w-4" />
                                </Button>
                            </div>
                        ))}
                        <Button type="button" variant="outline" size="sm" onClick={addRow} className="gap-2 border-gray-600 text-gray-300">
                            <Plus className="h-4 w-4" />
                            Añadir ticker
                        </Button>
                    </div>

                    {error ? (
                        <p className="text-sm text-red-300" role="alert">{error}</p>
                    ) : null}

                    <div className="flex justify-end gap-2">
                        <Button type="button" variant="outline" onClick={() => setOpen(false)} className="border-gray-600 text-gray-300">
                            Cancelar
                        </Button>
                        <Button type="submit" disabled={pending}>
                            {pending ? 'Guardando…' : 'Guardar plan'}
                        </Button>
                    </div>
                </form>
            </DialogContent>
        </Dialog>
    );
}
