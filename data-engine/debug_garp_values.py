
import sys
import os

# Add modules to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.garp import analyze_stock_garp
import yfinance as yf

tickers = ['NVDA', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'TSLA', 'JPM', 'V', 'UNH', 'PG', 'KO']

print(f"{'Ticker':<8} | {'Price':<10} | {'SMA200':<10} | {'ROE %':<8} | {'PEG':<6} | {'Passes?'}")
print("-" * 75)

for ticker in tickers:
    try:
        # We try to use the function directly
        # If it returns None, we want to know why, so we replicate the logic here for debugging
        
        stock = yf.Ticker(ticker)
        
        # Fast info
        try:
            current_price = stock.fast_info.get('lastPrice', 0)
            sma200 = stock.fast_info.get('twoHundredDayAverage', 0)
        except:
            current_price = 0
            sma200 = 0
            
        # Info
        try:
            info = stock.info
            roe = info.get('returnOnEquity', 0) or 0
            peg = info.get('pegRatio')
            if peg is None:
                peg = info.get('trailingPegRatio')
            peg = peg or 0
        except:
            roe = 0
            peg = 0

        # Logic check
        passes = True
        fail_reason = ""
        
        if not current_price or not sma200 or current_price <= sma200:
            passes = False
            fail_reason += "Trend "
            
        if roe < 0.12:
            passes = False
            fail_reason += "ROE "
            
        if not peg or peg > 2.25 or peg <= 0:
            passes = False
            fail_reason += "PEG "
            
        print(f"{ticker:<8} | {current_price:<10.2f} | {sma200:<10.2f} | {roe*100:<8.2f} | {peg:<6.2f} | {'YES' if passes else 'NO (' + fail_reason.strip() + ')'}")
        
    except Exception as e:
        print(f"{ticker:<8} | ERROR: {str(e)}")
