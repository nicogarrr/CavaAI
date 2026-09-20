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
        <div className="space-y-8" role="status" aria-live="polite" aria-label="Cargando dashboard">
            <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-5 gap-4">
                {[1, 2, 3, 4, 5].map((i) => (
                    <StockCardSkeleton key={i} />
                ))}
            </div>
            <ChartLoadingSkeleton />
        </div>
    );
}

export default async function Home() {
    const userId = await getUserId();

    return (
        <div className="flex min-h-screen flex-col p-6 gap-8">
            <Suspense fallback={<DashboardSkeleton />}>
                <PersonalizedOverview userId={userId} />
            </Suspense>
            <Suspense fallback={<NewsLoadingSkeleton />}>
                <NewsSection />
            </Suspense>
        </div>
    );
}
