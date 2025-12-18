
import yfinance as yf
import pandas as pd
import requests
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

# Suppress warnings
warnings.filterwarnings("ignore")

def get_sp500_tickers():
    """Scrape S&P 500 tickers from Wikipedia."""
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        # Add headers to avoid 403 Forbidden
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # Read HTML from response text
        tables = pd.read_html(response.text)
        df = tables[0]
        tickers = df['Symbol'].tolist()
        # Clean tickers (replace . with - for yfinance, e.g., BRK.B -> BRK-B)
        tickers = [t.replace('.', '-') for t in tickers]
        return tickers
    except Exception as e:
        print(f"Error scraping S&P 500: {e}")
        return []

# ... imports
import requests
import time

def analyze_stock_garp(ticker):
    try:
        # Standard yfinance call (handles sessions internally)
        stock = yf.Ticker(ticker)
        
        # Use fast_info check first (less bandwidth)
        try:
            current_price = stock.fast_info.get('lastPrice')
            sma200 = stock.fast_info.get('twoHundredDayAverage')
        except Exception:
            # Fallback if fast_info fails (rare)
            return None

        if not current_price or not sma200:
             return None
             
        # Trend Filter: Price > SMA200
        if current_price <= sma200:
            return None 

        # Now fetch INFO (slower)
        try:
            info = stock.info
        except Exception:
            return None

        # Quality Filter: ROE > 12% (Relaxed from 15%)
        roe = info.get('returnOnEquity', 0)
        if roe is None or roe < 0.12: return None
        
        # Value Filter: PEG < 2.25 (Relaxed from 1.5)
        # Try multiple keys for PEG
        peg = info.get('pegRatio')
        if peg is None:
            peg = info.get('trailingPegRatio')
            
        # Verify valid PEG range
        if peg is None or peg > 2.25 or peg <= 0: return None
            
        return {
            "symbol": ticker,
            "companyName": info.get('longName', ticker),
            "price": current_price,
            "doe": roe * 100,
            "peg": peg,
            "sma200": sma200,
            "sector": info.get('sector', 'N/A'),
            "industry": info.get('industry', 'N/A')
        }
    except Exception as e:
        # print(f"Error analyzing {ticker}: {e}")
        return None

def run_garp_strategy(limit=10, max_workers=20):
    """
    Run the full GARP strategy on S&P 500.
    """
    print("Fetching S&P 500 tickers...")
    tickers = get_sp500_tickers()
    if not tickers:
        return {"error": "Could not fetch tickers"}
    
    print(f"Analyzing {len(tickers)} stocks with {max_workers} threads...")
    
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_ticker = {executor.submit(analyze_stock_garp, t): t for t in tickers}
        
        count = 0
        for future in as_completed(future_to_ticker):
            res = future.result()
            if res:
                results.append(res)
            count += 1
            if count % 50 == 0:
                print(f"Processed {count}/{len(tickers)}...")

    # Sort checks:
    # We want "Best" GARP. 
    # Usually: Lowest PEG is best value? Or highest ROE?
    # The user didn't specify sorting, but implied "Growth at Reasonable Price".
    # Let's sort by PEG (ascending) as primary "Reasonable Price" metric.
    
    results.sort(key=lambda x: x['peg'])
    
    return results[:limit]

if __name__ == "__main__":
    # Test run
    top_stocks = run_garp_strategy(limit=5)
    print("Top GARP Stocks:")
    for s in top_stocks:
        print(s)
