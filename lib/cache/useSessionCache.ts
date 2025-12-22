'use client';

/**
 * Client-side session cache hook
 * Persists data in sessionStorage to survive tab changes within the same browser session
 */

import { useState, useEffect, useCallback } from 'react';

interface CacheOptions {
    /** Time to live in minutes. Default: 30 minutes */
    ttlMinutes?: number;
}

interface CacheEntry<T> {
    data: T;
    timestamp: number;
    ttlMinutes: number;
}

/**
 * Hook to cache data in sessionStorage with TTL
 * Data persists across tab changes but clears on browser close
 */
export function useSessionCache<T>(
    cacheKey: string,
    options: CacheOptions = {}
): {
    data: T | null;
    setData: (data: T) => void;
    clearCache: () => void;
    isFromCache: boolean;
} {
    const { ttlMinutes = 30 } = options;
    const [data, setDataState] = useState<T | null>(null);
    const [isFromCache, setIsFromCache] = useState(false);

    // Load from sessionStorage on mount
    useEffect(() => {
        if (typeof window === 'undefined') return;

        try {
            const stored = sessionStorage.getItem(cacheKey);
            if (stored) {
                const entry: CacheEntry<T> = JSON.parse(stored);
                const now = Date.now();
                const expiryTime = entry.timestamp + (entry.ttlMinutes * 60 * 1000);

                if (now < expiryTime) {
                    setDataState(entry.data);
                    setIsFromCache(true);
                } else {
                    // Expired, remove it
                    sessionStorage.removeItem(cacheKey);
                }
            }
        } catch (error) {
            console.warn('Failed to load from session cache:', error);
        }
    }, [cacheKey]);

    const setData = useCallback((newData: T) => {
        setDataState(newData);
        setIsFromCache(false);

        if (typeof window === 'undefined') return;

        try {
            const entry: CacheEntry<T> = {
                data: newData,
                timestamp: Date.now(),
                ttlMinutes,
            };
            sessionStorage.setItem(cacheKey, JSON.stringify(entry));
        } catch (error) {
            console.warn('Failed to save to session cache:', error);
        }
    }, [cacheKey, ttlMinutes]);

    const clearCache = useCallback(() => {
        setDataState(null);
        setIsFromCache(false);

        if (typeof window === 'undefined') return;

        try {
            sessionStorage.removeItem(cacheKey);
        } catch (error) {
            console.warn('Failed to clear session cache:', error);
        }
    }, [cacheKey]);

    return { data, setData, clearCache, isFromCache };
}

/**
 * Hook to cache stock-related data
 * Convenience wrapper with stock-specific key prefixes
 */
export function useStockCache<T>(
    symbol: string,
    dataType: string,
    options: CacheOptions = {}
) {
    const cacheKey = `stock-${dataType}-${symbol.toUpperCase()}`;
    return useSessionCache<T>(cacheKey, options);
}

/**
 * Hook to cache portfolio analysis data
 */
export function usePortfolioCache<T>(
    userId: string | undefined,
    dataType: string,
    options: CacheOptions = {}
) {
    const cacheKey = userId ? `portfolio-${dataType}-${userId}` : `portfolio-${dataType}`;
    return useSessionCache<T>(cacheKey, options);
}
