import { Suspense } from 'react';
import PersonalizedOverview from '@/components/PersonalizedOverview';
import NewsSection from '@/components/NewsSection';
import { ChartLoadingSkeleton, NewsLoadingSkeleton, StockCardSkeleton } from '@/components/LoadingState';
import { redirect } from 'next/navigation';
import { requireAuthenticatedUser } from '@/lib/auth/require-user';

// Forzar renderizado dinámico porque requiere datos de usuario
export const dynamic = 'force-dynamic';
export const revalidate = 0;

async function getUserId(): Promise<string> {
    try {
        return (await requireAuthenticatedUser()).id;
    } catch {
        redirect('/sign-in');
    }
}

function DashboardSkeleton() {
    return (
        <div className="space-y-8">
            {/* Una region live presente en el primer render nunca se anuncia: el
                texto va en un nodo sr-only y el esqueleto queda aria-hidden. */}
            <span className="sr-only">Cargando…</span>
            <div aria-hidden="true">
            <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-3 2xl:grid-cols-5 gap-4">
                {[1, 2, 3, 4, 5].map((i) => (
                    <StockCardSkeleton key={i} />
                ))}
            </div>
            <ChartLoadingSkeleton />
            </div>
        </div>
    );
}

export default async function Home() {
    const userId = await getUserId();

    return (
        <main id="content" tabIndex={-1} className="flex w-full max-w-full min-w-0 flex-col gap-6 overflow-x-clip p-4 sm:gap-8 sm:p-6">
            <Suspense fallback={<DashboardSkeleton />}>
                <PersonalizedOverview userId={userId} />
            </Suspense>
            <Suspense fallback={<NewsLoadingSkeleton />}>
                <NewsSection />
            </Suspense>
        </main>
    );
}
