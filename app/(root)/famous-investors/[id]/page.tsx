import { getFamousInvestorById } from '@/lib/actions/famousInvestors.actions';
import { notFound } from 'next/navigation';
import { Card } from '@/components/ui/card';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, TrendingUp, DollarSign } from 'lucide-react';
import Image from 'next/image';

type FamousInvestorDetailPageProps = {
    params: Promise<{
        id: string;
    }>;
};

export default async function FamousInvestorDetailPage({ params }: FamousInvestorDetailPageProps) {
    const { id } = await params;
    const investor = await getFamousInvestorById(id);

    if (!investor) {
        notFound();
    }

    return (
        <div className="flex min-h-screen flex-col p-6">
            <div className="mb-6">
                <Link href="/famous-investors">
                    <Button variant="ghost" size="sm" className="mb-4 gap-2">
                        <ArrowLeft className="h-4 w-4" />
                        Volver
                    </Button>
                </Link>
                
                <div className="flex items-start gap-6">
                    {investor.image && (
                        <div className="flex-shrink-0 w-24 h-24 relative rounded-full overflow-hidden border-2 border-gray-700">
                            <Image
                                src={investor.image}
                                alt={investor.name}
                                fill
                                className="object-cover"
                                unoptimized
                            />
                        </div>
                    )}
                    <div className="flex-1">
                        <h1 className="text-3xl font-bold text-gray-100 mb-2">{investor.name}</h1>
                        <p className="text-gray-400 mb-4">{investor.description}</p>
                        {investor.totalValue && (
                            <div className="flex items-center gap-2 text-lg text-gray-300">
                                <DollarSign className="h-5 w-5" />
                                <span className="font-semibold">
                                    Valor estimado: ${(investor.totalValue / 1000000000).toFixed(2)}B
                                </span>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
                <h2 className="text-xl font-semibold mb-6 text-gray-200">
                    Posiciones de la Cartera ({investor.positions.length} acciones)
                </h2>
                
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {investor.positions.map((position, index) => (
                        <Link
                            key={`${position.symbol}-${index}`}
                            href={`/stocks/${position.symbol}`}
                            className="block p-4 bg-gray-900/50 hover:bg-gray-900 rounded-lg border border-gray-700/50 transition-all duration-200 group"
                        >
                            <div className="flex items-center justify-between mb-2">
                                <h3 className="text-lg font-semibold text-gray-100 group-hover:text-teal-400 transition-colors">
                                    {position.symbol}
                                </h3>
                                <Badge variant="outline" className="text-xs">
                                    {position.source}
                                </Badge>
                            </div>
                            <p className="text-sm text-gray-400 line-clamp-1">{position.company}</p>
                            {position.percentage && (
                                <div className="mt-2 text-xs text-gray-500">
                                    {position.percentage.toFixed(2)}% de la cartera
                                </div>
                            )}
                        </Link>
                    ))}
                </div>
            </Card>
        </div>
    );
}

