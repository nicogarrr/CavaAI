"""
Yahoo Finance utilities for free financial data.
Uses yfinance library which is already installed for the GARP strategy.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional

def fetch_yf_dividends(symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Fetch dividend history from Yahoo Finance.
    
    Returns list of dividend records with format:
    [{
        "symbol": "AAPL",
        "date": "2024-11-14",
        "dividend": 0.25,
        "adjDividend": 0.25,
        "yield": null,  # Not available from yfinance directly
        "frequency": "Quarterly"  # Estimated from payment frequency
    }]
    """
    try:
        ticker = yf.Ticker(symbol)
        
        # Get dividend history
        dividends = ticker.dividends
        
        if dividends is None or dividends.empty:
            return []
        
        # Convert to list of dicts, most recent first
        result = []
        for date, amount in dividends.iloc[::-1].items():
            # Format label as "Month YYYY" for display
            label = date.strftime("%B %Y")
            result.append({
                "symbol": symbol.upper(),
                "date": date.strftime("%Y-%m-%d"),
                "label": label,
                "dividend": round(float(amount), 4),
                "adjDividend": round(float(amount), 4),
                "recordDate": "",
                "paymentDate": "",
                "declarationDate": "",
                "yield": None,
                "frequency": _estimate_frequency(dividends)
            })
            
            if len(result) >= limit:
                break
        
        return result
        
    except Exception as e:
        print(f"Error fetching Yahoo Finance dividends for {symbol}: {e}")
        return []

def _estimate_frequency(dividends) -> str:
    """Estimate dividend frequency based on payment intervals."""
    if len(dividends) < 2:
        return "Unknown"
    
    try:
        # Get average days between dividends
        dates = dividends.index.to_list()
        if len(dates) < 2:
            return "Unknown"
            
        intervals = []
        for i in range(1, min(5, len(dates))):  # Check last 4 intervals
            delta = (dates[-(i)] - dates[-(i+1)]).days
            intervals.append(abs(delta))
        
        avg_days = sum(intervals) / len(intervals)
        
        if avg_days < 45:
            return "Monthly"
        elif avg_days < 100:
            return "Quarterly"
        elif avg_days < 200:
            return "Semi-Annual"
        else:
            return "Annual"
    except:
        return "Quarterly"  # Default assumption

def fetch_yf_stock_info(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fetch basic stock info from Yahoo Finance.
    Useful for getting current dividend yield.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        return {
            "symbol": symbol.upper(),
            "dividendYield": info.get("dividendYield"),
            "dividendRate": info.get("dividendRate"),
            "exDividendDate": info.get("exDividendDate"),
            "lastDividendValue": info.get("lastDividendValue"),
            "lastDividendDate": info.get("lastDividendDate"),
        }
    except Exception as e:
        print(f"Error fetching Yahoo Finance info for {symbol}: {e}")
        return None

def fetch_yf_insider_trading(symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Fetch insider trading data from Yahoo Finance.
    Returns list of transactions formatted for the frontend.
    """
    try:
        ticker = yf.Ticker(symbol)
        
        # Get insider transactions
        # Returns a DataFrame with columns: 
        # ['Shares', 'Value', 'URL', 'Text', 'Insider', 'Position', 'Transaction', 'Start Date', 'Ownership']
        df = ticker.insider_transactions
        
        if df is None:
            return []
            
        if df.empty:
            return []
            
        result = []
        
        # Iterating through DataFrame rows
        for index, row in df.iterrows():
            # Calculate price per share if possible
            price = 0
            shares = row.get('Shares', 0)
            value = row.get('Value', 0)
            
            # Ensure numbers
            if not isinstance(shares, (int, float)): shares = 0
            if not isinstance(value, (int, float)): value = 0
            
            if shares > 0 and value > 0:
                price = value / shares
            
            # Format date
            date_str = ""
            start_date = row.get('Start Date')
            if pd.notnull(start_date):
                date_str = start_date.strftime("%Y-%m-%d")
                
            transaction = {
                "symbol": symbol.upper(),
                "filingDate": date_str,
                "transactionDate": date_str,
                "reportingName": str(row.get('Insider', 'Unknown')),
                "reportingTitle": str(row.get('Position', '')),
                "typeOfTransaction": str(row.get('Transaction', '')),
                "transactionType": str(row.get('Transaction', '')), # Keep for backward compatibility if needed, but primary is typeOfTransaction
                "typeOfOwner": "insider",
                "securitiesTransacted": int(shares),
                "price": float(price),
                "securitiesOwned": 0, # Not provided in this view
                "acquisitionOrDisposition": "A" if "Purchase" in str(row.get('Transaction', '')) else "D",
                "formType": "4",
                "url": str(row.get('URL', ''))
            }
            
            result.append(transaction)
            
            if len(result) >= limit:
                break
                
        return result
        
    except Exception as e:
        print(f"Error fetching Yahoo Finance insider trading for {symbol}: {e}")
        return []

def fetch_yf_batch_quotes(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Fetch quotes for multiple symbols at once using yfinance.
    Returns dict with symbol as key and quote data as value.
    """
    result = {}
    
    if not symbols:
        return result
    
    try:
        # Process in batches of 10 to avoid timeouts
        batch_size = 10
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            
            for symbol in batch:
                try:
                    ticker = yf.Ticker(symbol)
                    info = ticker.info
                    
                    # Get current price and basic info
                    current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
                    prev_close = info.get("previousClose", 0)
                    
                    result[symbol.upper()] = {
                        "symbol": symbol.upper(),
                        "price": current_price,
                        "change": round(current_price - prev_close, 2) if prev_close else 0,
                        "changePercent": round(((current_price - prev_close) / prev_close * 100), 2) if prev_close else 0,
                        "marketCap": info.get("marketCap", 0),
                        "companyName": info.get("shortName", symbol),
                        "open": info.get("open", 0),
                        "high": info.get("dayHigh", 0),
                        "low": info.get("dayLow", 0),
                        "volume": info.get("volume", 0),
                    }
                except Exception as e:
                    print(f"Error fetching quote for {symbol}: {e}")
                    result[symbol.upper()] = {
                        "symbol": symbol.upper(),
                        "price": 0,
                        "change": 0,
                        "changePercent": 0,
                        "marketCap": 0,
                        "companyName": symbol,
                    }
        
        return result
        
    except Exception as e:
        print(f"Error in batch quote fetch: {e}")
        return result


def fetch_yf_single_quote(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a single stock quote from Yahoo Finance.
    Returns quote data in Finnhub-compatible format.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        prev_close = info.get("previousClose", 0)
        
        return {
            "c": current_price,  # Current price
            "d": round(current_price - prev_close, 2) if prev_close else 0,  # Change
            "dp": round(((current_price - prev_close) / prev_close * 100), 2) if prev_close else 0,  # Change percent
            "h": info.get("dayHigh", 0),  # High
            "l": info.get("dayLow", 0),  # Low
            "o": info.get("open", 0),  # Open
            "pc": prev_close,  # Previous close
        }
    except Exception as e:
        print(f"Error fetching Yahoo Finance quote for {symbol}: {e}")
        return None


def fetch_yf_news(symbol: str, limit: int = 15) -> List[Dict[str, Any]]:
    """
    Fetch company news from Yahoo Finance.
    Returns list of news articles formatted for the frontend.
    """
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        
        if not news:
            return []
            
        result = []
        import hashlib
        from datetime import datetime as dt
        
        for i, article in enumerate(news):
            # New yfinance structure: data is nested under 'content'
            content = article.get("content", {})
            
            # Get ID
            article_id = article.get("id", "") or content.get("id", "")
            if not article_id:
                title = content.get("title", "")
                pub_date = content.get("pubDate", "")
                unique_str = f"{title}-{pub_date}-{i}"
                article_id = f"yf-{hashlib.md5(unique_str.encode()).hexdigest()[:12]}"
            
            # Parse date
            pub_date_str = content.get("pubDate", "")
            timestamp = 0
            if pub_date_str:
                try:
                    timestamp = int(dt.fromisoformat(pub_date_str.replace("Z", "+00:00")).timestamp())
                except:
                    pass
            
            # Get URL from clickThroughUrl or canonicalUrl
            url = ""
            if "clickThroughUrl" in content:
                url = content["clickThroughUrl"].get("url", "")
            if not url and "canonicalUrl" in content:
                url = content["canonicalUrl"].get("url", "")
            
            # Get provider/source
            source = ""
            if "provider" in content:
                source = content["provider"].get("displayName", "")
            
            # Get thumbnail
            image = ""
            if "thumbnail" in content:
                thumb = content["thumbnail"]
                if "resolutions" in thumb and thumb["resolutions"]:
                    # Get highest res
                    image = thumb["resolutions"][-1].get("url", "")
            
            item = {
                "id": article_id,
                "category": content.get("contentType", "company"),
                "datetime": timestamp,
                "headline": content.get("title", ""),
                "image": image,
                "related": symbol.upper(),
                "source": source or "Yahoo Finance",
                "summary": content.get("summary", ""),
                "url": url,
            }
            
            result.append(item)
            
            if len(result) >= limit:
                break
                
        return result
    except Exception as e:
        print(f"Error fetching Yahoo Finance news for {symbol}: {e}")
        return []
