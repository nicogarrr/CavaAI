
import yfinance as yf

tickers = ['AAPL', 'MSFT', 'NVDA', 'GOOGL']

print("Checking PEG Ratios...")
for t in tickers:
    stock = yf.Ticker(t)
    try:
        peg = stock.info.get('pegRatio')
        print(f"{t}: PEG = {peg}")
    except Exception as e:
        print(f"{t}: Error {e}")
