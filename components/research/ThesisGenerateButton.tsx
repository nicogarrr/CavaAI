'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { BrainCircuit, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { getLatestThesisJob, getThesisJobStatus, startThesisJob, type ThesisJobStatus } from '@/lib/actions/thesis-jobs.actions';

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

export default function ThesisGenerateButton({ ticker, label = 'Generar tesis' }: { ticker: string; label?: string }) {
    const router = useRouter();
    const [job, setJob] = useState<ThesisJobStatus | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [recovering, setRecovering] = useState(true);
    const [recoveryCycle, setRecoveryCycle] = useState(0);
    const [starting, setStarting] = useState(false);
    const startingRef = useRef(false);

    const active = job !== null && ['queued', 'running', 'retrying', 'dispatch_failed'].includes(job.status);
    const busy = recovering || starting || active;

    useEffect(() => {
        let disposed = false;
        let timer: ReturnType<typeof setTimeout> | undefined;
        const recover = async () => {
            if (startingRef.current) return;
            try {
                const latest = await getLatestThesisJob(ticker);
                if (!disposed && !startingRef.current) {
                    setJob(latest);
                    setRecovering(false);
                    setError(null);
                }
            } catch {
                if (!disposed) {
                    setError('No se pudo recuperar la generación. Reintentando…');
                    timer = setTimeout(recover, POLL_MS);
                }
            }
        };
        // Losing the page unmounts this observer, not the server-side worker.
        void recover();
        const onVisible = () => {
            if (document.visibilityState === 'visible') void recover();
        };
        document.addEventListener('visibilitychange', onVisible);
        window.addEventListener('focus', recover);
        return () => {
            disposed = true;
            clearTimeout(timer);
            document.removeEventListener('visibilitychange', onVisible);
            window.removeEventListener('focus', recover);
        };
    }, [ticker, recoveryCycle]);

    const jobId = job?.id;
    useEffect(() => {
        if (!active || !jobId) return;
        let disposed = false;
        let timer: ReturnType<typeof setTimeout> | undefined;
        const tick = async () => {
            try {
                const next = await getThesisJobStatus(jobId);
                if (disposed) return;
                setJob(next);
                if (next.status === 'succeeded' || next.status === 'failed') {
                    router.refresh();
                    return;
                }
            } catch {
                // A failed poll must never cancel or re-enqueue server work.
            }
            if (!disposed) timer = setTimeout(tick, POLL_MS);
        };
        void tick();
        return () => {
            disposed = true;
            clearTimeout(timer);
        };
    }, [active, jobId, router]);

    const start = async () => {
        if (busy || startingRef.current) return;
        startingRef.current = true;
        setStarting(true);
        setError(null);
        try {
            setJob(await startThesisJob(ticker, true, crypto.randomUUID()));
        } catch {
            // Enqueue may have committed before the connection dropped. Read
            // it back rather than suggesting that another click is needed.
            try {
                setJob(await getLatestThesisJob(ticker));
            } catch {
                setRecovering(true);
            }
            setRecovering(true);
            setRecoveryCycle((cycle) => cycle + 1);
            setError('No se pudo confirmar el envío. Recuperando el estado del servidor…');
        } finally {
            startingRef.current = false;
            setStarting(false);
        }
    };

    const phaseLabel = job?.current_phase ? PHASE_LABELS[job.current_phase] ?? job.current_phase : null;
    const doneCount = job?.phases.filter((p) => p.status === 'succeeded').length ?? 0;

    return (
        <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3">
                <Button type="button" onClick={start} disabled={busy} aria-busy={busy}>
                    {busy ? (
                        <Loader2 aria-hidden="true" className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                        <BrainCircuit aria-hidden="true" className="mr-2 h-4 w-4" />
                    )}
                    {recovering ? 'Recuperando generación…' : starting ? 'Encolando…' : active ? 'Generando en segundo plano…' : label}
                </Button>
                {active ? (
                    <span className="text-sm text-gray-400">
                        {phaseLabel ?? (job?.status === 'dispatch_failed' ? 'Esperando reconexión de la cola' : job?.status === 'retrying' ? 'Reintentando en el servidor' : 'En cola')}
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
