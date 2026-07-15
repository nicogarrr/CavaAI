'use client';

import { useEffect } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <section className="mx-auto max-w-2xl rounded-lg border border-red-900/70 bg-red-950/20 p-6">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 text-red-300" />
        <div className="flex-1">
          <h1 className="text-lg font-semibold text-gray-100">No se pudo completar la operación</h1>
          <p className="mt-2 text-sm leading-6 text-gray-300">
            {error.message || 'Se produjo un error inesperado. Inténtalo de nuevo.'}
          </p>
          {error.digest ? <p className="mt-2 text-xs text-gray-500">Referencia: {error.digest}</p> : null}
          <Button className="mt-4" onClick={reset} type="button" variant="outline">
            <RotateCcw className="h-4 w-4" />
            Reintentar
          </Button>
        </div>
      </div>
    </section>
  );
}
