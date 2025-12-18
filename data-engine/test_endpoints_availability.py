import requests
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('FMP_API_KEY')
symbol = 'AAPL'

print(f"API Key loaded. Testing endpoints for {symbol}...\n")

endpoints_to_test = [
    # 1. Company Information / Peers
    ("Stock Peers (Globe)", f'https://financialmodelingprep.com/stable/stock-peers?symbol={symbol}&apikey={api_key}'),
    
    # 2. Financial Scores (Globe)
    ("Financial Scores (Globe)", f'https://financialmodelingprep.com/stable/financial-scores?symbol={symbol}&apikey={api_key}'),
    
    # 3. Dividends (Globe)
    ("Dividends (Globe)", f'https://financialmodelingprep.com/stable/dividends?symbol={symbol}&apikey={api_key}'),
    
    # 4. Dividends Calendar (Globe) - No symbol
    ("Dividends Calendar (Globe)", f'https://financialmodelingprep.com/stable/dividends-calendar?from=2023-01-01&to=2023-03-01&apikey={api_key}'),
    
    # 5. Enterprise Values (Globe)
    ("Enterprise Values (Globe)", f'https://financialmodelingprep.com/stable/enterprise-values?symbol={symbol}&apikey={api_key}'),
    
    # 6. Key Metrics TTM (Globe)
    ("Key Metrics TTM (Globe)", f'https://financialmodelingprep.com/stable/key-metrics-ttm?symbol={symbol}&apikey={api_key}'),
]

for name, url in endpoints_to_test:
    print(f"--- Testing: {name} ---")
    try:
        res = requests.get(url, timeout=10)
        print(f"Status: {res.status_code}")
        
        if res.status_code == 200:
            try:
                data = res.json()
                if isinstance(data, list):
                    print(f"Success. List length: {len(data)}")
                    if len(data) > 0:
                        print(f"Sample: {str(data[0])[:100]}...")
                elif isinstance(data, dict):
                     print(f"Success. Dict keys: {list(data.keys())}")
                else:
                    print("Success (unknown format)")
            except:
                print("JSON Decode Failed")
        elif res.status_code == 402:
            print("RESTRICTED (402)")
        else:
            print(f"Error: {res.status_code}")
            
    except Exception as e:
        print(f"Exception: {e}")
    print("")
