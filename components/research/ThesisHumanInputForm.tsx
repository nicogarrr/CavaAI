'use client';

import { useState } from 'react';
import { submitThesisHumanInput } from '@/lib/actions/research.actions';
import { Button } from '@/components/ui/button';

export default function ThesisHumanInputForm({ ticker }: { ticker: string }) {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    setMessage(null);
    try {
      await submitThesisHumanInput(ticker, new FormData(event.currentTarget));
      setMessage('Supuesto guardado. Regenera la tesis para incorporarlo; no se ha convertido en un dato verificado.');
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'No se pudo guardar el supuesto.');
    } finally {
      setPending(false);
    }
  };

  const inputClass = 'mt-1 w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-100';

  return (
    <details className="rounded-lg border border-gray-800 p-4">
      <summary className="cursor-pointer text-sm font-semibold text-gray-200">Aportar un supuesto humano</summary>
      <p className="mt-2 text-xs leading-5 text-gray-400">
        Se guarda como supuesto, con fuente y justificación. Usa la clave exacta de un driver del modelo,
        por ejemplo revenue. Un dato financiero pendiente no se completa con un supuesto como si fuera un hecho.
      </p>
      <form onSubmit={submit} className="mt-3 space-y-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="text-xs text-gray-300">Clave del driver
            <input name="driver_key" required maxLength={160} className={inputClass} placeholder="revenue" />
          </label>
          <label className="text-xs text-gray-300">Ejercicio fiscal
            <input name="fiscal_year" type="number" required min={1900} max={2200} step={1} className={inputClass} />
          </label>
          <label className="text-xs text-gray-300">Escenario
            <select name="scenario" defaultValue="base" className={inputClass}>
              <option value="bear">Bear</option><option value="base">Base</option><option value="bull">Bull</option>
            </select>
          </label>
          <label className="text-xs text-gray-300">Valor (unidad del driver)
            <input name="value" type="number" required step="any" className={inputClass} />
          </label>
        </div>
        <label className="block text-xs text-gray-300">Fuente o referencia
          <input name="source" required maxLength={240} className={inputClass} />
        </label>
        <label className="block text-xs text-gray-300">Justificación
          <textarea name="rationale" required maxLength={5000} rows={3} className={inputClass} />
        </label>
        <Button type="submit" disabled={pending}>{pending ? 'Guardando...' : 'Guardar supuesto'}</Button>
        {message ? <p role="status" className="text-sm text-teal-300">{message}</p> : null}
        {error ? <p role="alert" className="text-sm text-red-300">{error}</p> : null}
      </form>
    </details>
  );
}
