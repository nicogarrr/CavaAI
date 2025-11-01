import { Card } from '@/components/ui/card';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { ArrowRight, TrendingUp, Users } from 'lucide-react';
import Image from 'next/image';

interface FamousInvestor {
    _id: string;
    name: string;
    description: string;
    image?: string;
    positions: Array<{
        symbol: string;
        company: string;
    }>;
    totalValue?: number;
}

interface FamousInvestorCardProps {
    investor: FamousInvestor;
}

export default function FamousInvestorCard({ investor }: FamousInvestorCardProps) {
    return (
        <Link href={`/famous-investors/${investor._id}`}>
            <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50 hover:bg-gray-800 transition-all duration-200 group cursor-pointer">
                <div className="flex items-start gap-4">
                    {investor.image && (
                        <div className="flex-shrink-0 w-16 h-16 relative rounded-full overflow-hidden border-2 border-gray-700">
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
                        <h3 className="text-lg font-semibold text-gray-100 group-hover:text-teal-400 transition-colors mb-1">
                            {investor.name}
                        </h3>
                        <p className="text-sm text-gray-400 mb-3 line-clamp-2">
                            {investor.description}
                        </p>
                        <div className="flex items-center gap-4 text-xs text-gray-500">
                            <div className="flex items-center gap-1">
                                <Users className="h-3 w-3" />
                                <span>{investor.positions.length} posiciones</span>
                            </div>
                            {investor.totalValue && (
                                <div className="flex items-center gap-1">
                                    <TrendingUp className="h-3 w-3" />
                                    <span>${(investor.totalValue / 1000000000).toFixed(1)}B</span>
                                </div>
                            )}
                        </div>
                        <div className="flex flex-wrap gap-2 mt-3">
                            {investor.positions.slice(0, 5).map((position) => (
                                <span
                                    key={position.symbol}
                                    className="px-2 py-1 bg-gray-900 text-gray-300 rounded text-xs font-medium"
                                >
                                    {position.symbol}
                                </span>
                            ))}
                            {investor.positions.length > 5 && (
                                <span className="px-2 py-1 bg-gray-900 text-gray-400 rounded text-xs">
                                    +{investor.positions.length - 5}
                                </span>
                            )}
                        </div>
                    </div>
                    <ArrowRight className="h-5 w-5 text-gray-500 group-hover:text-teal-400 transition-colors flex-shrink-0" />
                </div>
            </Card>
        </Link>
    );
}

