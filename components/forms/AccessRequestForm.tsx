'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { requestAccess } from '@/lib/actions/access-request.actions';
import { ACCESS_REQUEST_LIMITS } from '@/lib/access-request';

/**
 * Formulario "Pedir acceso" (registro cerrado). El campo `honeypot` va oculto a
 * las personas: si un bot lo rellena, el servidor responde bien y no guarda nada.
 */
export default function AccessRequestForm() {
    const [pending, setPending] = useState(false);
    const [done, setDone] = useState<string | null>(null);
    const [error, setError] = useState<{ message: string; field?: string } | null>(null);

    async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setPending(true);
        setError(null);
        try {
            const result = await requestAccess({
                name: form.get('name'),
                email: form.get('email'),
                note: form.get('note'),
                honeypot: form.get('website'),
            });
            if (result.ok) setDone(result.message);
            else setError({ message: result.message, field: result.field });
        } catch {
            setError({ message: 'No hemos podido enviar la solicitud. Inténtalo de nuevo.' });
        } finally {
            setPending(false);
        }
    }

    if (done) {
        return (
            <div role="status" className="rounded-lg border border-teal-900/60 bg-teal-950/20 p-4 text-sm leading-6 text-teal-100">
                {done}
            </div>
        );
    }

    return (
        <form onSubmit={onSubmit} className="space-y-5" aria-label="Pedir acceso a GerarAI" noValidate>
            <div>
                <label htmlFor="ar-name" className="form-label mb-2 block">Nombre</label>
                <input id="ar-name" name="name" required maxLength={ACCESS_REQUEST_LIMITS.nameMax} autoComplete="name" className="form-input block w-full" aria-invalid={error?.field === 'name'} />
            </div>
            <div>
                <label htmlFor="ar-email" className="form-label mb-2 block">Email</label>
                <input id="ar-email" name="email" type="email" required maxLength={ACCESS_REQUEST_LIMITS.emailMax} autoComplete="email" className="form-input block w-full" aria-invalid={error?.field === 'email'} />
            </div>
            <div>
                <label htmlFor="ar-note" className="form-label mb-2 block">Nota (opcional)</label>
                <textarea id="ar-note" name="note" rows={5} maxLength={ACCESS_REQUEST_LIMITS.noteMax} placeholder="Qué quieres analizar con GerarAI" className="form-input block min-h-36 overflow-y-auto w-full resize-y" aria-invalid={error?.field === 'note'} />
            </div>
            {/* Campo trampa: fuera de pantalla y fuera del orden de tabulacion. */}
            <div aria-hidden="true" className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
                <label htmlFor="ar-website">No rellenar</label>
                <input id="ar-website" name="website" tabIndex={-1} autoComplete="off" />
            </div>
            {error ? <p role="alert" className="text-sm text-red-400">{error.message}</p> : null}
            <Button type="submit" size="lg" disabled={pending} className="w-full">
                {pending ? 'Enviando…' : 'Pedir acceso'}
            </Button>
        </form>
    );
}
