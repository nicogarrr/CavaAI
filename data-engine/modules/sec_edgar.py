"""
SEC EDGAR utilities for free insider trading data.
Uses the official SEC EDGAR API which is free and public.
"""

import requests
from datetime import datetime
from typing import List, Dict, Any, Optional

# SEC EDGAR API base URL
SEC_BASE_URL = "https://data.sec.gov"

# Required headers for SEC API (they require a User-Agent)
SEC_HEADERS = {
    "User-Agent": "StockAnalysisTool/1.0 (analysis@stocktool.com)",
    "Accept": "application/json"
}

# Cache for CIK lookups (symbol -> CIK)
_cik_cache: Dict[str, str] = {}
_company_tickers: Optional[Dict] = None

def _load_company_tickers() -> Dict:
    """Load the SEC company tickers mapping (cached)."""
    global _company_tickers
    
    if _company_tickers is not None:
        return _company_tickers
    
    try:
        url = "https://www.sec.gov/files/company_tickers.json"
        response = requests.get(url, headers=SEC_HEADERS, timeout=15)
        
        if response.status_code == 200:
            _company_tickers = response.json()
            return _company_tickers
    except Exception as e:
        print(f"Error loading SEC company tickers: {e}")
    
    return {}

def _get_cik_for_symbol(symbol: str) -> Optional[str]:
    """
    Get the CIK (Central Index Key) for a stock symbol from SEC.
    """
    symbol = symbol.upper()
    
    if symbol in _cik_cache:
        return _cik_cache[symbol]
    
    tickers = _load_company_tickers()
    
    # Search for symbol in the company tickers
    for entry in tickers.values():
        if entry.get("ticker", "").upper() == symbol:
            cik = str(entry.get("cik_str", "")).zfill(10)
            _cik_cache[symbol] = cik
            return cik
    
    return None

def fetch_sec_insider_trading(symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Fetch insider trading data from SEC EDGAR Form 4 filings.
    """
    symbol = symbol.upper()
    
    try:
        # Get CIK for the symbol
        cik = _get_cik_for_symbol(symbol)
        
        if not cik:
            print(f"Could not find CIK for {symbol}")
            return []
        
        # Fetch company filings from SEC
        url = f"{SEC_BASE_URL}/submissions/CIK{cik}.json"
        response = requests.get(url, headers=SEC_HEADERS, timeout=15)
        
        if response.status_code != 200:
            print(f"SEC API error {response.status_code} for {symbol}")
            return []
        
        data = response.json()
        company_name = data.get("name", "Unknown")
        
        # Extract Form 4 filings (insider transaction reports)
        filings = data.get("filings", {}).get("recent", {})
        
        if not filings:
            return []
        
        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        accession_numbers = filings.get("accessionNumber", [])
        primary_documents = filings.get("primaryDocument", [])
        
        result = []
        
        for i, form in enumerate(forms):
            if form == "4" and len(result) < limit:  # Form 4 = Insider transaction
                accession = accession_numbers[i].replace("-", "") if i < len(accession_numbers) else ""
                clean_cik = cik.lstrip("0")
                
                result.append({
                    "symbol": symbol,
                    "filingDate": dates[i] if i < len(dates) else "",
                    "transactionDate": dates[i] if i < len(dates) else "",
                    "reportingName": company_name,
                    "reportingCik": clean_cik,
                    "transactionType": "Form 4 - Insider Transaction",
                    "typeOfOwner": "insider",
                    "securitiesTransacted": 0,
                    "price": 0,
                    "securitiesOwned": 0,
                    "acquisitionOrDisposition": "",
                    "formType": "4",
                    "url": f"https://www.sec.gov/Archives/edgar/data/{clean_cik}/{accession}/{primary_documents[i] if i < len(primary_documents) else ''}"
                })
        
        return result
        
    except Exception as e:
        print(f"Error fetching SEC insider trading for {symbol}: {e}")
        return []
