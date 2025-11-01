'use client';

import { Button } from '@/components/ui/button';
import { ArrowLeft } from 'lucide-react';
import { useRouter } from 'next/navigation';
import CreatePortfolioButton from './CreatePortfolioButton';

type PortfolioHeaderProps = {
    portfolio: {
        id: string;
        name: string;
        description?: string;
    };
};

export default function PortfolioHeader({ portfolio }: PortfolioHeaderProps) {
    const router = useRouter();

    return (
        <div className="flex items-start justify-between w-full">
            <div className="flex items-start gap-4">
                <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => router.push('/portfolio')}
                >
                    <ArrowLeft className="h-5 w-5" />
                </Button>
                <div>
                    <h1 className="text-3xl font-bold">{portfolio.name}</h1>
                    {portfolio.description && (
                        <p className="text-muted-foreground mt-2">{portfolio.description}</p>
                    )}
                </div>
            </div>
            <CreatePortfolioButton />
        </div>
    );
}

