import Link from 'next/link';

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-2xl flex-col items-center justify-center px-6 text-center">
      <p className="mb-3 text-sm font-medium uppercase tracking-[0.18em] text-emerald-400">CavaAI</p>
      <h1 className="text-3xl font-semibold text-white">Página no encontrada</h1>
      <p className="mt-3 max-w-lg text-sm leading-6 text-gray-400">
        La ruta que buscas no existe o ha cambiado. Vuelve al inicio para continuar tu análisis.
      </p>
      <Link
        className="mt-6 rounded-lg border border-emerald-500/50 px-4 py-2 text-sm font-medium text-emerald-300 transition-colors hover:bg-emerald-500/10 focus:outline-none focus:ring-2 focus:ring-emerald-400"
        href="/"
      >
        Volver al inicio
      </Link>
    </main>
  );
}
