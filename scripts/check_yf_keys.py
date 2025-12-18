
import yfinance as yf
import json

try:
    stock = yf.Ticker('AAPL')
    info = stock.info
    print("Keys found:", list(info.keys()))
    print("pegRatio:", info.get('pegRatio'))
    print("trailingPE:", info.get('trailingPE'))
    print("forwardPE:", info.get('forwardPE'))
    print("earningsGrowth:", info.get('earningsGrowth'))
except Exception as e:
    print("Error fetching info:", e)
