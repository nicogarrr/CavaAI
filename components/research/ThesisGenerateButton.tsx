'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { BrainCircuit, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { getThesisJobStatus, startThesisJob, type ThesisJobStatus } from '@/lib/actions/thesis-jobs.actions';

const PHASE_LABELS: Record<string, string> = {
    collect_evidence: 'Recopilando evidencia (SEC, noticias, filings)',
    build_fundamental_model: 'Construyendo modelo fundamental',
    run_valuation: 'Ejecutando valoración determinista',
    persist_valuation_snapshot: 'Guardando valoración y snapshot',
    source_audit: 'Auditoría de fuentes y claims',
    compose_thesis: 'Redactando la tesis',
    persist_thesis: 'Persistiendo la versión',
};

const POLL_MS = 3000;

export default function ThesisGenerateButton({ ticker }: { ticker: string }) {
    const router = useRouter();
    const [job, setJob] = useState<ThesisJobStatus | null>(null);
    const [error, setError] = useState<string | null>(null);
    const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

    const active = job !== null && (job.status === 'queued' || job.status === 'running');

    useEffect(() => {
        if (!active || !job) return;
        const tick = async () => {
            try {
                const next = await getThesisJobStatus(job.id);
                setJob(next);
                if (next.status === 'succeeded' || next.status === 'failed') {
                    router.refresh();
                    return;
                }
            } catch {
                // un fallo de sondeo no mata el seguimiento; reintenta en el próximo ciclo
            }
            timer.current = setTimeout(tick, POLL_MS);
        };
        timer.current = setTimeout(tick, POLL_MS);
        return () => {
            if (timer.current) clearTimeout(timer.current);
        };
    }, [active, job, router]);

    const start = async () => {
        setError(null);
        try {
            setJob(await startThesisJob(ticker));
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'No se pudo encolar la generación');
        }
    };

    const phaseLabel = job?.current_phase ? PHASE_LABELS[job.current_phase] ?? job.current_phase : null;
    const doneCount = job?.phases.filter((p) => p.status === 'succeeded').length ?? 0;

    return (
        <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3">
                <Button type="button" onClick={start} disabled={active}>
                    {active ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                        <BrainCircuit className="mr-2 h-4 w-4" />
                    )}
                    {active ? 'Generando en segundo plano…' : 'Generate thesis'}
                </Button>
                {active ? (
                    <span className="text-sm text-gray-400">
                        {phaseLabel ?? 'En cola'}
                        {doneCount > 0 ? ` · ${doneCount} fases completadas` : ''}
                    </span>
                ) : null}
            </div>
            {job?.status === 'succeeded' ? (
                <p className="text-sm text-teal-300">
                    Tesis v{job.result?.version} generada ({job.result?.status}).
                </p>
            ) : null}
            {job?.status === 'failed' ? (
                <p className="text-sm text-red-300">
                    La generación falló{job.error_class ? ` (${job.error_class})` : ''}. Puedes reintentar.
                </p>
            ) : null}
            {error ? <p className="text-sm text-red-300">{error}</p> : null}
        </div>
    );
}
