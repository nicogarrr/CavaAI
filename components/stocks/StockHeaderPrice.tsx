'use client';

import { useState, useEffect } from 'react';
import { getStockQuote } from '@/lib/actions/finnhub.actions';
import { ArrowUp, ArrowDown } from 'lucide-react';

interface StockHeaderPriceProps {
    symbol: string;
    initialPrice: number;
    initialChange: number;
    initialChangePercent: number;
}

export default function StockHeaderPrice({
    symbol,
    initialPrice,
    initialChange,
    initialChangePercent
}: StockHeaderPriceProps) {
    const [price, setPrice] = useState(initialPrice);
    const [change, setChange] = useState(initialChange);
    const [changePercent, setChangePercent] = useState(initialChangePercent);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        // Poll every 30 seconds
        const interval = setInterval(async () => {
            try {
                // Don't set loading state to avoid flickering, just update if successful
                const quote = await getStockQuote(symbol);
                if (quote && quote.c) {
                    setPrice(quote.c);
                    setChange(quote.d);
                    setChangePercent(quote.dp);
                }
            } catch (error) {
                console.error("Failed to update price:", error);
            }
        }, 30000);

        return () => clearInterval(interval);
    }, [symbol]);

    const isPositive = change >= 0;
    const isZero = change === 0;

    return (
        <div className="text-right">
            <p className="text-2xl font-bold text-gray-100 flex items-center justify-end gap-2">
                ${price.toFixed(2)}
            </p>
            <p className={`text-sm font-medium flex items-center justify-end gap-1 ${isZero ? 'text-gray-400' : isPositive ? 'text-green-400' : 'text-red-400'
                }`}>
                {isPositive ? '+' : ''}{change.toFixed(2)} ({isPositive ? '+' : ''}{changePercent.toFixed(2)}%)
            </p>
        </div>
    );
}
