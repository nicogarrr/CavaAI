'use client';

import { Skeleton } from '@/components/ui/skeleton';

/**
 * Reusable loading states for better UX
 * Improves perceived performance during data fetching
 */

export function NewsLoadingSkeleton() {
    return (
        <div className="w-full min-w-0 h-full bg-[#0F0F0F] rounded-lg border border-gray-800 p-4 sm:p-6" role="status" aria-live="polite" aria-label="Cargando noticias">
            <Skeleton className="h-8 w-48 max-w-full mb-4 sm:mb-6" />
            <div className="space-y-3 sm:space-y-4">
                {[1, 2, 3, 4, 5, 6].map((i) => (
                    <div key={i} className="p-4 bg-[#141414] rounded-lg border border-gray-800">
                        <div className="flex flex-col min-[420px]:flex-row gap-3 sm:gap-4">
                            <Skeleton className="h-40 w-full min-[420px]:h-24 min-[420px]:w-32 shrink-0 rounded-lg" />
                            <div className="flex-1 min-w-0 space-y-2">
                                <Skeleton className="h-5 w-full" />
                                <Skeleton className="h-5 w-3/4" />
                                <Skeleton className="h-4 w-full" />
                                <Skeleton className="h-4 w-2/3" />
                                <div className="flex gap-2">
                                    <Skeleton className="h-3 w-20" />
                                    <Skeleton className="h-3 w-24" />
                                </div>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

export function StockCardSkeleton() {
    return (
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-4" role="status" aria-live="polite" aria-label="Cargando tarjeta de acción">
            <div className="flex justify-between items-start mb-4">
                <div className="space-y-2">
                    <Skeleton className="h-6 w-32" />
                    <Skeleton className="h-4 w-24" />
                </div>
                <Skeleton className="h-8 w-16" />
            </div>
            <div className="space-y-2">
                <Skeleton className="h-8 w-24" />
                <Skeleton className="h-4 w-full" />
            </div>
        </div>
    );
}

export function ChartLoadingSkeleton() {
    return (
        <div className="w-full min-w-0 bg-gray-800 rounded-lg border border-gray-700 p-4 sm:p-6" role="status" aria-live="polite" aria-label="Cargando gráfico">
            <Skeleton className="h-8 w-48 max-w-full mb-4" />
            <Skeleton className="h-48 sm:h-64 w-full" />
        </div>
    );
}

export function TableLoadingSkeleton({ rows = 5 }: { rows?: number }) {
    return (
        <div className="w-full min-w-0 bg-gray-800 rounded-lg border border-gray-700 p-4" role="status" aria-live="polite" aria-label="Cargando tabla">
            <div className="space-y-3">
                <div className="flex flex-wrap gap-3 pb-2 border-b border-gray-700">
                    <Skeleton className="h-5 flex-1 min-w-[100px]" />
                    <Skeleton className="h-5 flex-1 min-w-[100px]" />
                    <Skeleton className="hidden min-[420px]:block h-5 flex-1 min-w-[80px]" />
                    <Skeleton className="hidden min-[420px]:block h-5 flex-1 min-w-[80px]" />
                </div>
                {Array.from({ length: rows }).map((_, i) => (
                    <div key={i} className="flex flex-wrap gap-3">
                        <Skeleton className="h-6 flex-1 min-w-[100px]" />
                        <Skeleton className="h-6 flex-1 min-w-[100px]" />
                        <Skeleton className="hidden min-[420px]:block h-6 flex-1 min-w-[80px]" />
                        <Skeleton className="hidden min-[420px]:block h-6 flex-1 min-w-[80px]" />
                    </div>
                ))}
            </div>
        </div>
    );
}

/**
 * Clases Tailwind cerradas: Tailwind solo genera las clases que ve literales
 * en el código, así que width/height se resuelven con mapas fijos
 * (nunca con interpolación `w-${...}` / `h-${...}`, que no genera CSS).
 */
const GENERIC_WIDTH_CLASSES = {
    sm: 'w-full max-w-sm',
    md: 'w-full max-w-2xl',
    lg: 'w-full max-w-4xl',
    full: 'w-full',
} as const;

const GENERIC_HEIGHT_CLASSES = {
    sm: 'h-24',
    md: 'h-48',
    lg: 'h-64',
} as const;

export function GenericLoadingSkeleton({
    width = 'full',
    height = 'md'
}: {
    width?: keyof typeof GENERIC_WIDTH_CLASSES;
    height?: keyof typeof GENERIC_HEIGHT_CLASSES;
}) {
    return (
        <div className={`${GENERIC_WIDTH_CLASSES[width]} bg-gray-800 rounded-lg border border-gray-700 p-6`} role="status" aria-live="polite" aria-label="Cargando contenido">
            <div className="space-y-4">
                <Skeleton className={`h-6 w-3/4`} />
                <Skeleton className={`${GENERIC_HEIGHT_CLASSES[height]} w-full`} />
            </div>
        </div>
    );
}
