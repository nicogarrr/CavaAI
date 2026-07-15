'use client';

import type { ReactNode } from 'react';
import { BarChart3, Building2 } from 'lucide-react';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

export function CompanyWorkspaceTabs({
    overview,
    market,
}: {
    overview: ReactNode;
    market: ReactNode;
}) {
    return (
        <Tabs defaultValue="overview" className="w-full">
            <TabsList className="mb-6 border border-gray-800 bg-[#0a0a0a]">
                <TabsTrigger value="overview" className="gap-2">
                    <Building2 className="h-4 w-4" />
                    Research workspace
                </TabsTrigger>
                <TabsTrigger value="market" className="gap-2">
                    <BarChart3 className="h-4 w-4" />
                    Market & chart
                </TabsTrigger>
            </TabsList>
            <TabsContent value="overview" className="mt-0">{overview}</TabsContent>
            <TabsContent value="market" className="mt-0">{market}</TabsContent>
        </Tabs>
    );
}
