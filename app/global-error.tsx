'use client';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="es">
      <body>
        <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center gap-4 p-6 text-center">
          <h1 className="text-2xl font-bold text-gray-100">Algo ha fallado</h1>
          <p className="text-sm text-gray-400">
            {error?.message ?? 'Error inesperado en la aplicación.'}
          </p>
          <button
            type="button"
            onClick={() => reset()}
            className="rounded-md bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-500"
          >
            Reintentar
          </button>
        </main>
      </body>
    </html>
  );
}
