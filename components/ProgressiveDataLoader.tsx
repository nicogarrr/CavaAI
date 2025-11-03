'use client';

import React, { useState, useEffect, ReactNode } from 'react';
import { Skeleton } from '@/components/ui/skeleton';

/**
 * Progressive data loader that shows cached data first, then updates with fresh data
 * Improves perceived performance and app fluidity
 */

interface ProgressiveDataLoaderProps<T> {
    fetchData: () => Promise<T>;
    cacheKey: string;
    cacheDuration?: number; // in milliseconds
    children: (data: T | null, isLoading: boolean, isStale: boolean) => ReactNode;
    fallback?: ReactNode;
}

export function ProgressiveDataLoader<T>({
    fetchData,
    cacheKey,
    cacheDuration = 60000, // 1 minute default
    children,
    fallback = <Skeleton className="h-20 w-full" />,
}: ProgressiveDataLoaderProps<T>) {
    const [data, setData] = useState<T | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isStale, setIsStale] = useState(false);

    useEffect(() => {
        let mounted = true;

        const loadData = async () => {
            try {
                // Check cache first
                const cached = getCachedData<T>(cacheKey);
                if (cached) {
                    if (mounted) {
                        setData(cached.data);
                        setIsLoading(false);
                        setIsStale(Date.now() - cached.timestamp > cacheDuration);
                    }
                }

                // Fetch fresh data
                const freshData = await fetchData();
                
                if (mounted) {
                    setData(freshData);
                    setIsLoading(false);
                    setIsStale(false);
                    setCachedData(cacheKey, freshData);
                }
            } catch (error) {
                console.error('Error loading data:', error);
                if (mounted) {
                    setIsLoading(false);
                }
            }
        };

        loadData();

        return () => {
            mounted = false;
        };
    }, [cacheKey, fetchData, cacheDuration]);

    if (isLoading && !data) {
        return <>{fallback}</>;
    }

    return <>{children(data, isLoading, isStale)}</>;
}

// Simple localStorage-based cache for client-side data
function getCachedData<T>(key: string): { data: T; timestamp: number } | null {
    if (typeof window === 'undefined') return null;
    
    try {
        const cached = localStorage.getItem(`cache_${key}`);
        if (cached) {
            return JSON.parse(cached);
        }
    } catch (error) {
        console.warn('Error reading cache:', error);
    }
    return null;
}

function setCachedData<T>(key: string, data: T): void {
    if (typeof window === 'undefined') return;
    
    try {
        const cacheData = {
            data,
            timestamp: Date.now(),
        };
        localStorage.setItem(`cache_${key}`, JSON.stringify(cacheData));
    } catch (error) {
        console.warn('Error writing cache:', error);
    }
}
