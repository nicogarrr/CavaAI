/**
 * Utilities for parallel data fetching to improve app fluidity
 * Fetches from multiple sources simultaneously and returns first successful result
 */

/**
 * Race multiple data sources and return first successful result
 * Improves perceived performance by using fastest available source
 */
export async function raceDataSources<T>(
    fetchers: Array<() => Promise<T | null>>,
    fallbackValue: T | null = null
): Promise<T | null> {
    const promises = fetchers.map((fetcher) => 
        fetcher().catch((error) => {
            console.warn('Data source error:', error);
            return null;
        })
    );

    // Race all promises and return first non-null result
    const results = await Promise.race([
        Promise.all(promises),
        ...promises.map((p) => p.then((result) => result ? [result] : null)),
    ]);

    if (Array.isArray(results)) {
        // Find first non-null result
        for (const result of results) {
            if (result !== null) return result;
        }
    }

    return fallbackValue;
}

/**
 * Fetch from multiple sources in parallel and combine results
 * Useful for aggregating data from multiple APIs
 */
export async function parallelFetch<T>(
    fetchers: Array<() => Promise<T | null>>,
    combiner?: (results: Array<T | null>) => T | null
): Promise<T | null> {
    const promises = fetchers.map((fetcher) => 
        fetcher().catch((error) => {
            console.warn('Parallel fetch error:', error);
            return null;
        })
    );

    const results = await Promise.all(promises);

    if (combiner) {
        return combiner(results);
    }

    // Default: return first non-null result
    for (const result of results) {
        if (result !== null) return result;
    }

    return null;
}

/**
 * Fetch with timeout to prevent slow requests from blocking the UI
 */
export async function fetchWithTimeout<T>(
    fetcher: () => Promise<T>,
    timeoutMs: number = 10000
): Promise<T | null> {
    const timeoutPromise = new Promise<null>((resolve) => {
        setTimeout(() => resolve(null), timeoutMs);
    });

    try {
        const result = await Promise.race([fetcher(), timeoutPromise]);
        return result;
    } catch (error) {
        console.warn('Fetch with timeout error:', error);
        return null;
    }
}

/**
 * Batch multiple API calls with delay to respect rate limits
 */
export async function batchWithDelay<T>(
    items: T[],
    processor: (item: T) => Promise<any>,
    delayMs: number = 100
): Promise<any[]> {
    const results: any[] = [];
    
    for (let i = 0; i < items.length; i++) {
        const result = await processor(items[i]);
        results.push(result);
        
        // Add delay between requests (except for last one)
        if (i < items.length - 1) {
            await new Promise(resolve => setTimeout(resolve, delayMs));
        }
    }
    
    return results;
}
