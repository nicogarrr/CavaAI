'use client';

import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, ExternalLink, Star } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useRouter } from 'next/navigation';
import Image from 'next/image';

type FundData = {
  symbol: string;
  profile: {
    ticker?: string;
    name?: string;
    exchange?: string;
    currency?: string;
    country?: string;
    ipo?: string;
    logo?: string;
    weburl?: string;
  };
  holdings: Array<{
    symbol?: string;
    name?: string;
    percent?: number;
  }>;
  candles: {
    c: number[];
    t: number[];
    o: number[];
    h: number[];
    l: number[];
    v: number[];
  } | null;
};

type FundHeaderProps = {
  fundData: FundData;
};

export default function FundHeader({ fundData }: FundHeaderProps) {
  const router = useRouter();
  const { symbol, profile } = fundData;

  const currentPrice = fundData.candles?.c?.[fundData.candles.c.length - 1] || 0;
  const previousPrice = fundData.candles?.c?.[fundData.candles.c.length - 2] || currentPrice;
  const change = currentPrice - previousPrice;
  const changePercent = previousPrice > 0 ? (change / previousPrice) * 100 : 0;

  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => router.back()}
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
            
            <div className="flex items-start gap-4">
              {profile.logo && (
                <div className="w-16 h-16 rounded-lg overflow-hidden bg-muted flex items-center justify-center">
                  <Image
                    src={profile.logo}
                    alt={`${profile.name} logo`}
                    width={64}
                    height={64}
                    className="object-contain"
                  />
                </div>
              )}
              
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <h1 className="text-3xl font-bold">{profile.name || symbol}</h1>
                  <Badge variant="secondary" className="text-sm">
                    {symbol}
                  </Badge>
                </div>
                
                <div className="flex items-center gap-4 text-sm text-muted-foreground">
                  {profile.exchange && (
                    <span>Exchange: {profile.exchange}</span>
                  )}
                  {profile.currency && (
                    <span>Currency: {profile.currency}</span>
                  )}
                  {profile.country && (
                    <span>Country: {profile.country}</span>
                  )}
                </div>
                
                {profile.weburl && (
                  <a
                    href={profile.weburl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800"
                  >
                    <ExternalLink className="h-4 w-4" />
                    Website oficial
                  </a>
                )}
              </div>
            </div>
          </div>
          
          <div className="text-right space-y-2">
            <div className="text-3xl font-bold">
              ${currentPrice.toFixed(2)}
            </div>
            <div className={`text-lg font-semibold ${change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {change >= 0 ? '+' : ''}{change.toFixed(2)} ({changePercent >= 0 ? '+' : ''}{changePercent.toFixed(2)}%)
            </div>
            <div className="flex items-center gap-2">
              <Star className="h-4 w-4 text-yellow-500" />
              <span className="text-sm text-muted-foreground">ETF</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
