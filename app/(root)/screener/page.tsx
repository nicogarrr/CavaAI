import { Suspense } from 'react';
import ScreenerFilters from '@/components/screener/ScreenerFilters';
import ScreenerResults from '@/components/screener/ScreenerResults';
import ScreenerHeader from '@/components/screener/ScreenerHeader';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

// Forzar renderizado dinámico
export const dynamic = 'force-dynamic';

export default function ScreenerPage() {
  return (
    <div className="flex min-h-screen flex-col p-6">
      <ScreenerHeader />
      
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mt-6">
        {/* Sidebar con filtros */}
        <div className="lg:col-span-1">
          <Card>
            <CardContent className="p-6">
              <ScreenerFilters />
            </CardContent>
          </Card>
        </div>
        
        {/* Resultados */}
        <div className="lg:col-span-3">
          <Suspense fallback={
            <Card>
              <CardContent className="p-6">
                <div className="space-y-4">
                  <Skeleton className="h-8 w-64" />
                  <Skeleton className="h-4 w-32" />
                  <div className="space-y-2">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <Skeleton key={i} className="h-16 w-full" />
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          }>
            <ScreenerResults />
          </Suspense>
        </div>
      </div>
    </div>
  );
}
