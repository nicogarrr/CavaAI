
import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('FMP_API_KEY')

def test_screener():
    # Test company-screener
    # Docs say: company-screener
    url = f"https://financialmodelingprep.com/stable/company-screener?limit=5&apikey={api_key}"
    print(f"Testing Company Screener: {url.replace(api_key, 'HIDDEN')}")
    res = requests.get(url).json()
    if res and isinstance(res, list):
        print("Company Screener Result (First item):", res[0] if res else "No results")
        print("Keys:", res[0].keys() if res else "N/A")
    else:
        print("Result:", res)

if __name__ == "__main__":
    test_screener()
