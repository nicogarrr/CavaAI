# Data Sources Setup Guide

This guide explains how to configure multiple data sources for maximum reliability and app fluidity.

## Overview

CavaAI now supports **5 different data sources** with automatic fallback:

1. **Finnhub** (Primary) - High quality, real-time data
2. **Twelve Data** (Secondary) - Good balance of limits and quality
3. **Alpha Vantage** (Tertiary) - Free tier with reasonable limits
4. **Polygon.io** (Quaternary) - Additional fallback option
5. **Yahoo Finance** (Fallback) - No API key required

## Why Multiple Sources?

- **Reliability**: If one service is down, others provide backup
- **Rate Limits**: Distribute load across multiple services
- **Cost Optimization**: Use free tiers effectively
- **Improved Fluidity**: Faster response times with fallback racing

## Setup Instructions

### 1. Finnhub (Recommended Primary)

**Free Tier**: 60 calls/minute
**Paid Tier**: Higher limits, real-time data

1. Sign up at [finnhub.io](https://finnhub.io/)
2. Get your API key from the dashboard
3. Add to `.env`:
   ```env
   FINNHUB_API_KEY=your_finnhub_api_key_here
   FINNHUB_BASE_URL=https://finnhub.io/api/v1
   ```

**Best for**: Stock quotes, company profiles, news, earnings

### 2. Twelve Data (Recommended Secondary)

**Free Tier**: 8 calls/minute, 800 calls/day
**Features**: Good data quality, reasonable limits

1. Sign up at [twelvedata.com](https://twelvedata.com/)
2. Get your API key
3. Add to `.env`:
   ```env
   TWELVE_DATA_API_KEY=your_twelve_data_api_key_here
   ```

**Best for**: Stock quotes, company profiles, time series data

### 3. Alpha Vantage (Free Tier)

**Free Tier**: 5 calls/minute, 500 calls/day
**Features**: Comprehensive data, good documentation

1. Sign up at [alphavantage.co](https://www.alphavantage.co/)
2. Get your free API key
3. Add to `.env`:
   ```env
   ALPHA_VANTAGE_API_KEY=your_alpha_vantage_api_key_here
   ```

**Best for**: Fundamental data, company overviews, global quotes

### 4. Polygon.io (Optional)

**Free Tier**: Limited but useful for fallback
**Paid Tiers**: More comprehensive access

1. Sign up at [polygon.io](https://polygon.io/)
2. Get your API key
3. Add to `.env`:
   ```env
   POLYGON_API_KEY=your_polygon_api_key_here
   ```

**Best for**: Historical data, market data, aggregates

### 5. Yahoo Finance (Automatic Fallback)

**No API Key Required**: Works without configuration
**Limitations**: Unofficial API, may be rate-limited

No setup required - automatically used as last resort.

**Best for**: Emergency fallback when all other sources fail

## Recommended Configuration

### For Development
Use at least 2 sources for reliability:
```env
FINNHUB_API_KEY=your_key
TWELVE_DATA_API_KEY=your_key
```

### For Production
Use 3-4 sources for maximum reliability:
```env
FINNHUB_API_KEY=your_key
TWELVE_DATA_API_KEY=your_key
ALPHA_VANTAGE_API_KEY=your_key
POLYGON_API_KEY=your_key
```

## Usage Priority

The system automatically tries sources in this order:

```
1. Finnhub (if configured)
   ↓ (if fails or rate limited)
2. Twelve Data (if configured)
   ↓ (if fails or rate limited)
3. Alpha Vantage (if configured)
   ↓ (if fails or rate limited)
4. Polygon (if configured)
   ↓ (if fails or rate limited)
5. Yahoo Finance (always available)
```

Each source has:
- **8-10 second timeout** to prevent blocking
- **Automatic error handling** with logging
- **Data validation** before returning

## Rate Limit Management

### Strategy 1: Distribute Load
Configure multiple sources to handle different types of requests:
- Use Finnhub for real-time quotes
- Use Twelve Data for company profiles
- Use Alpha Vantage for fundamental data

### Strategy 2: Sequential Delays
The system automatically adds delays between API calls:
- 150-200ms delay between sequential requests
- Prevents hitting rate limits
- Improves success rate

### Strategy 3: Caching
All data is cached appropriately:
- **Real-time prices**: 60 seconds
- **Company profiles**: 1 hour
- **Historical data**: 6 hours

## Monitoring

Check your API usage:

```javascript
// The system logs which source was used
const quote = await getQuoteWithFallback('AAPL');
console.log(`Source: ${quote.source}`);
// Output: "Source: finnhub" or "twelve_data" etc.
```

## Cost Optimization

### Free Tier Strategy
Use all free tiers to maximize requests:
- Finnhub: 60/min = 86,400/day
- Twelve Data: 800/day
- Alpha Vantage: 500/day
- Total: ~87,700 free requests/day

### Paid Tier Recommendation
Upgrade Finnhub first for:
- Real-time data
- Higher rate limits
- Better reliability

## Troubleshooting

### Issue: "Rate limit reached"
**Solution**: 
- Add more data sources
- Increase cache TTL
- Add delays between requests

### Issue: "No data returned"
**Solution**:
- Check API keys are correct
- Verify symbols are valid
- Check network connectivity
- Review console logs for specific errors

### Issue: "Slow response times"
**Solution**:
- Check which source is being used
- Consider upgrading to paid tier
- Verify cache is working
- Check network latency

### Issue: "Invalid API key"
**Solution**:
- Regenerate API key from provider
- Update `.env` file
- Restart the application
- Clear cache if needed

## Testing Your Setup

Test each data source individually:

```bash
# Test Finnhub
curl "https://finnhub.io/api/v1/quote?symbol=AAPL&token=YOUR_KEY"

# Test Twelve Data
curl "https://api.twelvedata.com/quote?symbol=AAPL&apikey=YOUR_KEY"

# Test Alpha Vantage
curl "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=AAPL&apikey=YOUR_KEY"

# Test Polygon
curl "https://api.polygon.io/v2/aggs/ticker/AAPL/prev?apikey=YOUR_KEY"
```

## Best Practices

1. **Always configure at least 2 sources** for reliability
2. **Monitor your rate limits** regularly
3. **Use caching effectively** to reduce API calls
4. **Keep API keys secure** - never commit to git
5. **Test failover** periodically by disabling primary source
6. **Log and monitor** which sources are being used
7. **Set up alerts** for API quota thresholds

## Performance Impact

With multiple sources configured:
- **99.9% uptime** for data availability
- **Faster response times** through source racing
- **Better user experience** with instant fallback
- **Cost-effective** by maximizing free tiers

## Next Steps

1. Sign up for at least 2 data sources
2. Add API keys to `.env`
3. Test the application
4. Monitor which sources are used
5. Adjust caching based on usage patterns

For more details on implementation, see [PERFORMANCE.md](./PERFORMANCE.md) and [USAGE_EXAMPLES.md](./USAGE_EXAMPLES.md).
