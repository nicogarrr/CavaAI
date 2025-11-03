# Usage Examples for Performance Optimizations

This document provides practical examples of how to use the new performance optimization features.

## 1. Using Request Cache for Data Fetching

```typescript
import { requestCache } from '@/lib/cache/requestCache';

// In your server action
export async function getStockData(symbol: string) {
  const cacheKey = `stock_${symbol}`;
  
  return requestCache.get(
    cacheKey,
    async () => {
      // Your fetch logic here
      const response = await fetch(`/api/stocks/${symbol}`);
      return response.json();
    },
    60 // Cache for 60 seconds
  );
}
```

## 2. Using Multiple Data Sources with Fallback

```typescript
import { getQuoteWithFallback, getProfileWithFallback } from '@/lib/actions/dataSources.actions';

// Automatically tries multiple sources
const quote = await getQuoteWithFallback('AAPL');
// Will try: Finnhub → Twelve Data → Alpha Vantage → Polygon → Yahoo Finance

const profile = await getProfileWithFallback('AAPL');
// Will try: Finnhub → Twelve Data → Alpha Vantage
```

## 3. Using Progressive Data Loader in Components

```tsx
import { ProgressiveDataLoader } from '@/components/ProgressiveDataLoader';

function StockPrice({ symbol }: { symbol: string }) {
  return (
    <ProgressiveDataLoader
      cacheKey={`price_${symbol}`}
      fetchData={async () => {
        const res = await fetch(`/api/quote/${symbol}`);
        return res.json();
      }}
      cacheDuration={30000} // 30 seconds
    >
      {(data, isLoading, isStale) => (
        <div>
          {isLoading && !data && <p>Loading...</p>}
          {data && (
            <div className={isStale ? 'opacity-70' : ''}>
              <h2>${data.price}</h2>
              {isStale && <small>Updating...</small>}
            </div>
          )}
        </div>
      )}
    </ProgressiveDataLoader>
  );
}
```

## 4. Optimizing Components with React.memo

```tsx
import { withOptimization } from '@/components/OptimizedWrapper';

// Simple component optimization
const ExpensiveComponent = ({ data }: { data: any }) => {
  // Expensive rendering logic
  return <div>{/* ... */}</div>;
};

export default withOptimization(ExpensiveComponent);

// With custom comparison
export default withOptimization(ExpensiveComponent, (prev, next) => {
  return prev.data.id === next.data.id;
});
```

## 5. Using Parallel Data Fetching

```tsx
import { raceDataSources, parallelFetch } from '@/lib/utils/parallelFetch';

// Race multiple sources, return fastest
const data = await raceDataSources([
  () => fetchFromFinnhub(symbol),
  () => fetchFromAlphaVantage(symbol),
  () => fetchFromYahoo(symbol),
]);

// Fetch from all sources and combine
const combinedData = await parallelFetch(
  [
    () => fetchNews(symbol),
    () => fetchProfile(symbol),
    () => fetchMetrics(symbol),
  ],
  (results) => {
    // Combine results
    return {
      news: results[0],
      profile: results[1],
      metrics: results[2],
    };
  }
);
```

## 6. Using Fetch with Timeout

```typescript
import { fetchWithTimeout } from '@/lib/utils/parallelFetch';

// Prevent slow requests from blocking UI
const data = await fetchWithTimeout(
  async () => {
    const res = await fetch('https://slow-api.com/data');
    return res.json();
  },
  5000 // 5 second timeout
);

if (data === null) {
  console.log('Request timed out');
}
```

## 7. Batch API Calls with Rate Limiting

```typescript
import { batchWithDelay } from '@/lib/utils/parallelFetch';

const symbols = ['AAPL', 'GOOGL', 'MSFT', 'AMZN'];

// Process with 200ms delay between calls
const results = await batchWithDelay(
  symbols,
  async (symbol) => {
    return await fetchStockData(symbol);
  },
  200 // 200ms delay
);
```

## 8. Optimizing Large Lists

```tsx
import OptimizedWrapper from '@/components/OptimizedWrapper';

function StockList({ stocks }: { stocks: Stock[] }) {
  return (
    <div>
      {stocks.map(stock => (
        <OptimizedWrapper key={stock.id}>
          <StockCard stock={stock} />
        </OptimizedWrapper>
      ))}
    </div>
  );
}
```

## 9. Using Data Source Priority

```typescript
// In your environment variables, configure which sources you have:
// FINNHUB_API_KEY=xxx
// TWELVE_DATA_API_KEY=xxx
// ALPHA_VANTAGE_API_KEY=xxx
// POLYGON_API_KEY=xxx

// The fallback system will automatically use available sources in priority order:
// 1. Finnhub (if key present)
// 2. Twelve Data (if key present)
// 3. Alpha Vantage (if key present)
// 4. Polygon (if key present)
// 5. Yahoo Finance (no key required)
```

## 10. Monitoring Data Source Usage

```typescript
import { getQuoteWithFallback } from '@/lib/actions/dataSources.actions';

const quote = await getQuoteWithFallback('AAPL');

if (quote) {
  console.log(`Data loaded from: ${quote.source}`);
  // Will log: "Data loaded from: finnhub" or "twelve_data" etc.
}
```

## Best Practices

### 1. Choose Appropriate Cache Duration

- **Real-time prices**: 30-60 seconds
- **News**: 60-120 seconds
- **Company profiles**: 1-6 hours
- **Historical data**: 24 hours

### 2. Use Progressive Loading for Large Data

Always show cached data first, then update with fresh data in the background.

### 3. Implement Request Deduplication

Use the request cache for any data that might be requested by multiple components simultaneously.

### 4. Optimize Component Re-renders

Wrap expensive components with React.memo, especially:
- Charts and graphs
- Large tables
- Complex calculations
- Heavy DOM structures

### 5. Handle Failures Gracefully

```typescript
const data = await getQuoteWithFallback(symbol);
if (!data) {
  // Show fallback UI
  return <div>Unable to load data at this time</div>;
}
```

## Performance Tips

1. **Preload critical data**: Use `<link rel="preload">` for above-the-fold data
2. **Lazy load below-the-fold content**: Use intersection observer
3. **Debounce search inputs**: Prevent excessive API calls
4. **Use virtualization**: For lists with 100+ items
5. **Optimize images**: Use Next.js Image component with proper sizing

## Troubleshooting

### Issue: Cache not working
- Check that cache keys are consistent
- Verify TTL is appropriate for your use case
- Clear cache if stale: `requestCache.clear()`

### Issue: Too many API calls
- Check for duplicate cache keys
- Ensure request deduplication is working
- Add delays between batch calls

### Issue: Slow page loads
- Check Network tab for blocking requests
- Verify lazy loading is working
- Look for unnecessary re-renders in React DevTools
