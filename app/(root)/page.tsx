import { Suspense } from 'react';
import PersonalizedOverview from '@/components/PersonalizedOverview';
import { Loader2 } from 'lucide-react';
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

function LoadingSkeleton() {
    return (
        <div className="flex items-center justify-center min-h-[400px]">
            <Loader2 className="h-8 w-8 animate-spin text-teal-500" />
            <span className="ml-3 text-gray-400">Cargando tu dashboard...</span>
        </div>
    );
}

export default async function Home() {
    const userId = await getUserId();

    return (
        <div className="flex min-h-screen flex-col p-6">
            <Suspense fallback={<LoadingSkeleton />}>
                <PersonalizedOverview userId={userId} />
            </Suspense>
        </div>
    );
}
