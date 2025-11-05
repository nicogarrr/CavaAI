'use client';

import { Skeleton } from '@/components/ui/skeleton';

/**
 * Reusable loading states for better UX
 * Improves perceived performance during data fetching
 */

export function NewsLoadingSkeleton() {
    return (
        <div className="w-full h-full bg-[#0F0F0F] rounded-lg border border-gray-800 p-6" role="status" aria-live="polite" aria-label="Cargando noticias">
            <Skeleton className="h-8 w-48 mb-6" />
            <div className="space-y-4">
                {[1, 2, 3, 4, 5, 6].map((i) => (
                    <div key={i} className="p-4 bg-[#141414] rounded-lg border border-gray-800">
                        <div className="flex gap-4">
                            <Skeleton className="flex-shrink-0 w-32 h-24 rounded-lg" />
                            <div className="flex-1 space-y-2">
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
        <div className="w-full bg-gray-800 rounded-lg border border-gray-700 p-6" role="status" aria-live="polite" aria-label="Cargando gráfico">
            <Skeleton className="h-8 w-48 mb-4" />
            <Skeleton className="h-64 w-full" />
        </div>
    );
}

export function TableLoadingSkeleton({ rows = 5 }: { rows?: number }) {
    return (
        <div className="w-full bg-gray-800 rounded-lg border border-gray-700 p-4" role="status" aria-live="polite" aria-label="Cargando tabla">
            <div className="space-y-3">
                <div className="flex gap-4 pb-2 border-b border-gray-700">
                    <Skeleton className="h-5 w-32" />
                    <Skeleton className="h-5 w-24" />
                    <Skeleton className="h-5 w-20" />
                    <Skeleton className="h-5 w-24" />
                </div>
                {Array.from({ length: rows }).map((_, i) => (
                    <div key={i} className="flex gap-4">
                        <Skeleton className="h-6 w-32" />
                        <Skeleton className="h-6 w-24" />
                        <Skeleton className="h-6 w-20" />
                        <Skeleton className="h-6 w-24" />
                    </div>
                ))}
            </div>
        </div>
    );
}

export function GenericLoadingSkeleton({ 
    width = 'full', 
    height = '64' 
}: { 
    width?: string; 
    height?: string 
}) {
    return (
        <div className={`w-${width} bg-gray-800 rounded-lg border border-gray-700 p-6`}>
            <div className="space-y-4">
                <Skeleton className={`h-6 w-3/4`} />
                <Skeleton className={`h-${height} w-full`} />
            </div>
        </div>
    );
}
