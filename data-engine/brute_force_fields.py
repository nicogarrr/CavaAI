from mstarpy import Funds
import datetime
import json

def test_nav():
    print("\nTesting Funds.nav...")
    try:
        # Use a known ISIN
        # f = Funds(term="Global", language="es", pageSize=1)
        # res = f.GetData(field="isin")
        # isin = res[0]['isin']
        isin = "LU0219441069" # Example
        print(f"Using ISIN: {isin}")
        
        fund = Funds(isin, language="es")
        end_date = datetime.datetime.now()
        start_date = end_date - datetime.timedelta(days=400) # Get > 1 year
        
        history = fund.nav(start_date=start_date, end_date=end_date)
        print(f"History items: {len(history)}")
        if history:
            print(f"First: {history[0]}")
            print(f"Last: {history[-1]}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_nav()
