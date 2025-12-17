import requests
import os
from dotenv import load_dotenv
from .storage import get_cached_data, save_to_cache

load_dotenv()
FMP_API_KEY = os.getenv('FMP_API_KEY')
BASE_URL = 'https://financialmodelingprep.com/stable'

def fetch_income_statement(symbol, period='annual'):
    url = f'{BASE_URL}/income-statement?symbol={symbol}' + f'&period={period}&apikey={FMP_API_KEY}'
    cache_key = f'income_{period}_{symbol}'
    cached = get_cached_data(symbol, cache_key, 86400)
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_balance_sheet(symbol, period='annual'):
    url = f'{BASE_URL}/balance-sheet-statement?symbol={symbol}' + f'&period={period}&apikey={FMP_API_KEY}'
    cache_key = f'balance_{period}_{symbol}'
    cached = get_cached_data(symbol, cache_key, 86400)
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_cash_flow(symbol, period='annual'):
    url = f'{BASE_URL}/cash-flow-statement?symbol={symbol}' + f'&period={period}&apikey={FMP_API_KEY}'
    cache_key = f'cashflow_{period}_{symbol}'
    cached = get_cached_data(symbol, cache_key, 86400)
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_financial_growth(symbol):
    url = f'{BASE_URL}/financial-growth?symbol={symbol}&apikey={FMP_API_KEY}'
    cache_key = f'growth_{symbol}'
    cached = get_cached_data(symbol, cache_key, 86400)
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_ratios_ttm(symbol):
    """Fetch TTM ratios: PER, ROIC, ROE, P/S, P/B calculated on trailing 12 months"""
    url = f'{BASE_URL}/ratios-ttm?symbol={symbol}&apikey={FMP_API_KEY}'
    cache_key = f'ratios_ttm_{symbol}'
    cached = get_cached_data(symbol, cache_key, 43200)  # 12h cache for TTM data
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_dcf(symbol):
    """Fetch Discounted Cash Flow - Intrinsic value calculated by FMP"""
    url = f'{BASE_URL}/discounted-cash-flow?symbol={symbol}&apikey={FMP_API_KEY}'
    cache_key = f'dcf_{symbol}'
    cached = get_cached_data(symbol, cache_key, 43200)  # 12h cache
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_enterprise_value(symbol):
    """Fetch Enterprise Value data for EV/EBITDA and EV/FCF calculations"""
    url = f'{BASE_URL}/enterprise-values?symbol={symbol}&apikey={FMP_API_KEY}'
    cache_key = f'ev_{symbol}'
    cached = get_cached_data(symbol, cache_key, 86400)  # 24h cache
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_key_metrics_ttm(symbol):
    """Fetch Key Metrics TTM: ROE, ROIC, EV/EBITDA, Graham Number, etc."""
    url = f'{BASE_URL}/key-metrics-ttm?symbol={symbol}&apikey={FMP_API_KEY}'
    cache_key = f'key_metrics_ttm_{symbol}'
    cached = get_cached_data(symbol, cache_key, 43200)  # 12h cache
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_financial_scores(symbol):
    """Fetch Financial Scores: Altman Z-Score + Piotroski Score"""
    url = f'{BASE_URL}/financial-scores?symbol={symbol}&apikey={FMP_API_KEY}'
    cache_key = f'scores_{symbol}'
    cached = get_cached_data(symbol, cache_key, 86400)  # 24h cache
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_owner_earnings(symbol):
    """Fetch Owner Earnings - Buffett's preferred metric"""
    url = f'{BASE_URL}/owner-earnings?symbol={symbol}&apikey={FMP_API_KEY}'
    cache_key = f'owner_earnings_{symbol}'
    cached = get_cached_data(symbol, cache_key, 86400)  # 24h cache
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_price_target_consensus(symbol):
    """Fetch Price Target Consensus: Analyst high/low/median targets"""
    url = f'{BASE_URL}/price-target-consensus?symbol={symbol}&apikey={FMP_API_KEY}'
    cache_key = f'price_target_{symbol}'
    cached = get_cached_data(symbol, cache_key, 21600)  # 6h cache
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_grades_consensus(symbol):
    """Fetch Stock Grades Consensus: Buy/Hold/Sell ratings"""
    url = f'{BASE_URL}/grades-consensus?symbol={symbol}&apikey={FMP_API_KEY}'
    cache_key = f'grades_{symbol}'
    cached = get_cached_data(symbol, cache_key, 21600)  # 6h cache
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_stock_peers(symbol):
    """Fetch Stock Peers for comparison"""
    url = f'{BASE_URL}/stock-peers?symbol={symbol}&apikey={FMP_API_KEY}'
    cache_key = f'peers_{symbol}'
    cached = get_cached_data(symbol, cache_key, 86400)  # 24h cache
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

# ============================================================================
# PRIORITY APIs - AI/RAG, Trading Signals, WACC
# ============================================================================

def fetch_earnings_transcript(symbol, year=None, quarter=None):
    """Fetch Earnings Call Transcript - GOLD for AI/RAG analysis"""
    # Build URL with optional year/quarter params
    url = f'{BASE_URL}/earning-call-transcript?symbol={symbol}&apikey={FMP_API_KEY}'
    if year:
        url += f'&year={year}'
    if quarter:
        url += f'&quarter={quarter}'
    
    cache_key = f'transcript_{symbol}_{year or "latest"}_{quarter or "all"}'
    cached = get_cached_data(symbol, cache_key, 604800)  # 7 days cache (transcripts don't change)
    if cached: return cached
    try:
        res = requests.get(url, timeout=30)  # Longer timeout for large text
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_insider_trading(symbol, limit=50):
    """Fetch Insider Trading data - CEO/CFO buy/sell signals"""
    url = f'{BASE_URL}/insider-trading?symbol={symbol}&limit={limit}&apikey={FMP_API_KEY}'
    cache_key = f'insider_{symbol}'
    cached = get_cached_data(symbol, cache_key, 21600)  # 6h cache
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_treasury_rates():
    """Fetch Treasury Rates - 10Y for Risk-Free Rate in WACC"""
    url = f'{BASE_URL}/treasury-rates?apikey={FMP_API_KEY}'
    cache_key = 'treasury_rates'
    cached = get_cached_data('MACRO', cache_key, 3600)  # 1h cache
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache('MACRO', cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_analyst_estimates(symbol, period='annual', limit=5):
    """Fetch Analyst Estimates - Future EPS/Revenue projections"""
    url = f'{BASE_URL}/analyst-estimates?symbol={symbol}&period={period}&limit={limit}&apikey={FMP_API_KEY}'
    cache_key = f'estimates_{period}_{symbol}'
    cached = get_cached_data(symbol, cache_key, 21600)  # 6h cache
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

def fetch_press_releases(symbol, limit=20):
    """Fetch Official Press Releases - Less noisy than general news"""
    url = f'{BASE_URL}/news/press-releases?symbols={symbol}&limit={limit}&apikey={FMP_API_KEY}'
    cache_key = f'press_{symbol}'
    cached = get_cached_data(symbol, cache_key, 3600)  # 1h cache
    if cached: return cached
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        save_to_cache(symbol, cache_key, data)
        return data
    except Exception as e:
        return {'error': str(e)}

