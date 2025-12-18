import requests
import os
from dotenv import load_dotenv
from .storage import get_cached_data, save_to_cache

load_dotenv()
FMP_API_KEY = os.getenv('FMP_API_KEY')
BASE_URL = 'https://financialmodelingprep.com/stable'

def _fetch_from_fmp(url, cache_key, symbol, ttl=86400):
    """Universal helper for FMP API calls with caching and error handling."""
    # Try Cache
    cached = get_cached_data(symbol, cache_key, ttl)
    if cached: return cached
    
    try:
        # print(f"DEBUG: Fetching FMP: {url.replace(FMP_API_KEY, 'HIDDEN')}")
        res = requests.get(url, timeout=15)
        
        # Handle non-200 responses
        if res.status_code != 200:
            if res.status_code in [402, 403]:
                # Plan restricted or forbidden - return empty instead of erroring
                # Most FMP endpoints return a list [ {...} ], so [] is safer
                print(f"DEBUG: FMP Restricted (Status {res.status_code}) for {symbol}")
                return []
            
            msg = f"FMP API Error {res.status_code}"
            return {'error': msg}
            
        # Try parse JSON
        try:
            data = res.json()
        except Exception as je:
            return {'error': f"JSON Parse Error: {je}. Body snippet: {res.text[:50]}"}
            
        # Save to cache if valid data
        if data is not None:
            save_to_cache(symbol, cache_key, data)
            
        return data
        
    except requests.exceptions.Timeout:
        return {'error': "FMP API Timeout"}
    except Exception as e:
        return {'error': f"Fetch Exception: {str(e)}"}

def fetch_income_statement(symbol, period='annual'):
    url = f'{BASE_URL}/income-statement?symbol={symbol}&period={period}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'income_{period}_{symbol}', symbol)

def fetch_balance_sheet(symbol, period='annual'):
    url = f'{BASE_URL}/balance-sheet-statement?symbol={symbol}&period={period}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'balance_{period}_{symbol}', symbol)

def fetch_cash_flow(symbol, period='annual'):
    url = f'{BASE_URL}/cash-flow-statement?symbol={symbol}&period={period}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'cashflow_{period}_{symbol}', symbol)

def fetch_financial_growth(symbol):
    url = f'{BASE_URL}/financial-growth?symbol={symbol}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'growth_{symbol}', symbol)

def fetch_ratios_ttm(symbol):
    url = f'{BASE_URL}/ratios-ttm?symbol={symbol}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'ratios_ttm_{symbol}', symbol, ttl=43200)

def fetch_dcf(symbol):
    url = f'{BASE_URL}/discounted-cash-flow?symbol={symbol}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'dcf_{symbol}', symbol, ttl=43200)

def fetch_enterprise_value(symbol):
    url = f'{BASE_URL}/enterprise-values?symbol={symbol}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'ev_{symbol}', symbol)

def fetch_key_metrics_ttm(symbol):
    url = f'{BASE_URL}/key-metrics-ttm?symbol={symbol}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'key_metrics_ttm_{symbol}', symbol, ttl=43200)

def fetch_financial_scores(symbol):
    url = f'{BASE_URL}/financial-scores?symbol={symbol}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'scores_{symbol}', symbol)

def fetch_owner_earnings(symbol):
    url = f'{BASE_URL}/owner-earnings?symbol={symbol}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'owner_earnings_{symbol}', symbol)

def fetch_price_target_consensus(symbol):
    url = f'{BASE_URL}/price-target-consensus?symbol={symbol}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'price_target_{symbol}', symbol, ttl=21600)

def fetch_grades_consensus(symbol):
    url = f'{BASE_URL}/grades-consensus?symbol={symbol}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'grades_{symbol}', symbol, ttl=21600)

def fetch_stock_peers(symbol):
    url = f'{BASE_URL}/stock-peers?symbol={symbol}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'peers_{symbol}', symbol)

def fetch_dividends(symbol, limit=20):
    url = f'{BASE_URL}/dividends?symbol={symbol}&limit={limit}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'dividends_{symbol}', symbol)

def fetch_earnings_transcript(symbol, year=None, quarter=None):
    url = f'{BASE_URL}/earning-call-transcript?symbol={symbol}&apikey={FMP_API_KEY}'
    if year: url += f'&year={year}'
    if quarter: url += f'&quarter={quarter}'
    cache_key = f'transcript_{symbol}_{year or "latest"}_{quarter or "all"}'
    return _fetch_from_fmp(url, cache_key, symbol, ttl=604800)

def fetch_insider_trading(symbol, limit=50):
    url = f'{BASE_URL.replace("stable", "v4")}/insider-trading?symbol={symbol}&limit={limit}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'insider_{symbol}', symbol, ttl=21600)

def fetch_treasury_rates():
    url = f'{BASE_URL}/treasury-rates?apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, 'treasury_rates', 'MACRO', ttl=3600)

def fetch_analyst_estimates(symbol, period='annual', limit=5):
    url = f'{BASE_URL}/analyst-estimates?symbol={symbol}&period={period}&limit={limit}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'estimates_{period}_{symbol}', symbol, ttl=21600)

def fetch_press_releases(symbol, limit=20):
    url = f'{BASE_URL}/news/press-releases?symbols={symbol}&limit={limit}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'press_{symbol}', symbol, ttl=3600)

def fetch_biggest_gainers():
    url = f'{BASE_URL}/biggest-gainers?apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, 'market_gainers', 'MARKET', ttl=300)

def fetch_biggest_losers():
    url = f'{BASE_URL}/biggest-losers?apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, 'market_losers', 'MARKET', ttl=300)

def fetch_most_actives():
    url = f'{BASE_URL}/most-actives?apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, 'market_active', 'MARKET', ttl=300)

def fetch_stock_screener(market_cap_more_than=None, sector=None, limit=20):
    url = f'{BASE_URL}/stock-screener?apikey={FMP_API_KEY}&limit={limit}'
    if market_cap_more_than: url += f'&marketCapMoreThan={market_cap_more_than}'
    if sector: url += f'&sector={sector}'
    cache_key = f'screener_{market_cap_more_than}_{sector}_{limit}'
    return _fetch_from_fmp(url, cache_key, 'MARKET', ttl=3600)

def fetch_earnings_transcripts_list(symbol):
    url = f'{BASE_URL.replace("stable", "v4")}/earning-call-transcript-dates?symbol={symbol}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'transcripts_list_{symbol}', symbol)

def fetch_fmp_articles(page=0, limit=20):
    url = f'{BASE_URL.replace("stable", "v3")}/fmp-articles?page={page}&limit={limit}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'fmp_articles_{page}_{limit}', 'MARKET', ttl=900)

def fetch_general_news(page=0, limit=20):
    url = f'{BASE_URL.replace("stable", "v4")}/general_news?page={page}&limit={limit}&apikey={FMP_API_KEY}'
    return _fetch_from_fmp(url, f'general_news_{page}_{limit}', 'MARKET', ttl=900)

