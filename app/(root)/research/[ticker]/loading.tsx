import { StockCardSkeleton } from '@/components/LoadingState';

export default function ResearchTickerLoading() {
  return (
    <main className="min-h-screen bg-[#080808] px-4 py-6 sm:px-6 lg:px-8" aria-live="polite" aria-label="Cargando ficha de research">
      <div className="mx-auto max-w-[1600px] space-y-6">
        <div className="h-8 w-48 animate-pulse rounded bg-gray-800" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <StockCardSkeleton key={i} />
          ))}
        </div>
      </div>
    </main>
  );
}
