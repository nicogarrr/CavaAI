"""
Fund Ranking Module - Dynamic Scraping from Finect.com using Selenium
Scrapes top performing investment funds from finect.com for Spanish investors.
Uses Selenium with headless Chrome for JavaScript execution.
Caches results for 30 days.
"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import json
import os
import datetime
import re
import time

CACHE_FILE = "funds_cache.json"
CACHE_DURATION_SECONDS = 30 * 24 * 3600  # 30 días

# Mapping of frontend category codes to Finect category name search terms
# Based on actual Finect category names extracted via Selenium (1166 funds, 65+ RV categories)
# Using partial match - search term must appear in the scraped category name
CATEGORY_FILTER_MAP = {
    # No filter - show all top funds
    "default": None,
    
    # GLOBAL / WORLD
    "world": "RV Global Cap.",  # Matches: RV Global Cap. Grande Blend/Growth/Value, RV Global Cap. Pequeña
    
    # USA / S&P 500
    "sp500": "RV USA Cap.",  # Matches: RV USA Cap. Grande Blend/Growth/Value, RV USA Cap. Mediana/Pequeña
    "eeuu": "RV USA Cap.",
    "usa": "RV USA Cap.",
    
    # TECHNOLOGY
    "tech": "RV Sector Tecnología",  # Exact match
    
    # EMERGING MARKETS
    "emergentes": "RV Global Emergente",  # Exact match
    
    # ASIA
    "asia": "RV Asia",  # Matches: RV Asia, RV Asia (ex-Japón), RV Asia Pacífico
    
    # GOLD & PRECIOUS METALS
    "oro": "RV Sector Oro y Metales Preciosos",  # Exact match
    "gold": "RV Sector Oro y Metales Preciosos",
    
    # SPAIN
    "espana": "RV España",  # Exact match
    
    # EUROPE
    "europa": "RV Europa Cap.",  # Matches: RV Europa Cap. Grande Blend/Growth/Value, RV Europa Cap. Mediana/Pequeña
    
    # SECTORS
    "energia": "RV Sector Energía",  # Matches: RV Sector Energía, RV Sector Energía Alternativa
    "biotech": "RV Sector Biotecnología",  # Exact match
    "salud": "RV Sector Salud",  # Exact match
    "finanzas": "RV Sector Finanzas",  # Exact match
    "infraestructura": "RV Sector Infraestructura",  # Exact match
    
    # COUNTRIES
    "japon": "RV Japón",  # Matches: RV Japón Cap. Grande, RV Japón Cap. Med/Peq
    "china": "RV China",  # Matches: RV China, RV China - A Shares
    "india": "RV India",  # Exact match
    "latam": "RV Latinoamérica",  # Exact match
}


def get_chrome_driver():
    """Creates a headless Chrome driver"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def extract_isin_from_url(url: str) -> str:
    """Extract ISIN from Finect fund URL like /fondos-inversion/LU0496367763-..."""
    match = re.search(r'/([A-Z]{2}[A-Z0-9]{9,10})-', url)
    if match:
        return match.group(1)
    return ""

def parse_percentage(text: str) -> float:
    """Extract numeric percentage from text like '156,67%' or '-5,67%'"""
    try:
        clean = text.replace('%', '').replace('.', '').replace(',', '.').strip()
        match = re.search(r'-?\d+\.?\d*', clean)
        if match:
            return float(match.group())
    except:
        pass
    return 0.0

def scrape_all_categories() -> list:
    """
    Scrapes all fund categories from Finect's categories page.
    Returns list of category dictionaries with id, name, and url.
    Results are cached for 30 days.
    """
    cache = {}
    cache_key = "_categories"
    
    # Try loading from cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                cached = cache.get(cache_key)
                if cached:
                    ts = cached.get('timestamp', 0)
                    if (datetime.datetime.now().timestamp() - ts) < CACHE_DURATION_SECONDS:
                        print("DEBUG: Serving categories from cache")
                        return cached['data']
        except:
            pass
    
    driver = None
    try:
        print("DEBUG: Scraping all categories from Finect...")
        driver = get_chrome_driver()
        driver.get("https://www.finect.com/fondos-inversion/categoria/todos")
        
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/categorias/']"))
        )
        time.sleep(2)
        
        categories = []
        seen_ids = set()
        
        # Find category links
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/fondos-inversion/categorias/']")
        
        for link in links:
            try:
                href = link.get_attribute('href')
                name = link.text.strip()
                
                if not name or len(name) < 3:
                    continue
                
                # Extract category ID from URL like /categorias/452-Rv_sector_oro
                match = re.search(r'/categorias/(\d+)-', href)
                if match:
                    cat_id = match.group(1)
                    if cat_id in seen_ids:
                        continue
                    seen_ids.add(cat_id)
                    
                    categories.append({
                        "id": cat_id,
                        "name": name,
                        "url": f"https://www.finect.com/fondos-inversion/listado?categories={cat_id}&order=-M12"
                    })
            except:
                continue
        
        print(f"DEBUG: Found {len(categories)} categories")
        
        # Save to cache
        cache[cache_key] = {
            "timestamp": datetime.datetime.now().timestamp(),
            "data": categories
        }
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
        
        return categories
        
    except Exception as e:
        print(f"Error scraping categories: {e}")
        # Return default categories
        return [
            {"id": "393", "name": "RV Global", "url": "https://www.finect.com/fondos-inversion/listado?categories=393&order=-M12"},
            {"id": "410", "name": "RV USA", "url": "https://www.finect.com/fondos-inversion/listado?categories=410&order=-M12"},
            {"id": "460", "name": "RV Sector Tecnología", "url": "https://www.finect.com/fondos-inversion/listado?categories=460&order=-M12"},
            {"id": "452", "name": "RV Sector Oro y Metales Preciosos", "url": "https://www.finect.com/fondos-inversion/listado?categories=452&order=-M12"},
        ]
    finally:
        if driver:
            driver.quit()

def scrape_finect_selenium(url: str, limit: int = 10, category_id: str = None) -> list:
    """
    Scrapes fund data from Finect.com using Selenium.
    If category_id is provided, applies the category filter via UI interaction.
    Returns list of fund dictionaries with name, ISIN, category, and performance.
    """
    driver = None
    try:
        print(f"DEBUG: Starting Selenium scraper for: {url[:60]}...")
        driver = get_chrome_driver()
        driver.get(url)
        
        # Wait for page to load (wait for table rows to appear)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table tr, .fund-row, [data-isin]"))
        )
        
        # If category_id is provided, apply the filter by clicking
        if category_id and category_id != 'default' and category_id.isdigit():
            try:
                print(f"DEBUG: Applying category filter: {category_id}")
                
                # Click on "Categoría" button to open filter dropdown
                cat_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Categoría')]"))
                )
                cat_button.click()
                time.sleep(1)
                
                # Find and click the category option by its data attribute or text
                # Finect uses checkboxes inside the dropdown
                category_option = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, f"input[value='{category_id}'], [data-category='{category_id}']"))
                )
                category_option.click()
                time.sleep(2)  # Wait for page to reload with filter
                
                print(f"DEBUG: Category filter applied")
            except Exception as filter_err:
                print(f"DEBUG: Could not apply category filter: {filter_err}")
                # Continue without filter - will scrape all funds
        
        # Scroll down to load more funds (Finect uses infinite scroll)
        # Each scroll loads ~24 more funds and takes ~5 seconds
        # For 1000+ funds, need ~50 scrolls (~4 minutes)
        scroll_count = min(limit // 24 + 1, 50)
        print(f"DEBUG: Will perform {scroll_count} scrolls to load ~{scroll_count * 24} funds")
        for i in range(scroll_count):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(5)  # Wait 5 seconds for content to load
            if i % 10 == 0:
                print(f"DEBUG: Scroll {i+1}/{scroll_count}")
        
        # Wait for final content to settle
        time.sleep(2)
        
        funds = []
        seen_isins = set()
        
        # Find all fund rows - Finect uses table rows
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        
        if not rows:
            # Try alternative selectors
            rows = driver.find_elements(By.CSS_SELECTOR, ".fund-item, .fund-row, [class*='fund']")
        
        print(f"DEBUG: Found {len(rows)} rows")
        
        for row in rows[:limit * 2]:  # Get extra in case some are invalid
            try:
                if len(funds) >= limit:
                    break
                
                # Try to find fund link
                link_elem = row.find_element(By.CSS_SELECTOR, "a[href*='/fondos-inversion/']")
                href = link_elem.get_attribute('href')
                name = link_elem.text.strip()
                
                if not name or len(name) < 5:
                    continue
                    
                isin = extract_isin_from_url(href)
                if not isin or isin in seen_isins:
                    continue
                    
                # Skip category/gestora links
                if 'categorias/' in href or 'gestoras/' in href:
                    continue
                
                seen_isins.add(isin)
                
                # Extract data from cells
                cells = row.find_elements(By.TAG_NAME, "td")
                
                return_12m = 0
                return_5y = 0
                category = ""
                gestora = ""
                
                for cell in cells:
                    text = cell.text.strip()
                    
                    # Check for percentage (contains % and arrow or just number%)
                    if '%' in text:
                        value = parse_percentage(text)
                        # First percentage is usually 12M return
                        if return_12m == 0 and value != 0:
                            return_12m = value
                        elif return_5y == 0 and value != 0:
                            return_5y = value
                    
                    # Check for category link
                    try:
                        cat_link = cell.find_element(By.CSS_SELECTOR, "a[href*='/categorias/']")
                        if cat_link:
                            category = cat_link.text.strip()
                    except:
                        pass
                    
                    # Check for gestora link
                    try:
                        gestora_link = cell.find_element(By.CSS_SELECTOR, "a[href*='/gestoras/']")
                        if gestora_link:
                            gestora = gestora_link.text.strip()
                    except:
                        pass
                
                funds.append({
                    "rank": 0,
                    "name": name[:80],
                    "isin": isin,
                    "gestora": gestora,
                    "tipo": "Fondo",
                    "category": category,
                    "return1Y": round(return_12m, 2),
                    "return3Y": 0,  # Would need different page for 3Y
                    "return5Y": round(return_5y, 2),
                    "volatility": 0,
                    "ter": 0
                })
                
            except Exception as e:
                # Row might not have expected structure
                continue
        
        print(f"DEBUG: Extracted {len(funds)} funds with Selenium")
        return funds
        
    except Exception as e:
        print(f"Error in Selenium scraper: {e}")
        return []
    finally:
        if driver:
            driver.quit()

def get_all_funds_cached() -> list:
    """
    Returns all funds from cache, or scrapes them if cache is expired/missing.
    Uses master cache key '_all_funds' which contains all 1000+ funds.
    Cache is valid for 30 days.
    """
    cache = {}
    cache_key = "_all_funds"
    
    # Load cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                cached_data = cache.get(cache_key)
                if cached_data:
                    ts = cached_data.get('timestamp', 0)
                    if (datetime.datetime.now().timestamp() - ts) < CACHE_DURATION_SECONDS:
                        print(f"DEBUG: Serving {len(cached_data['data'])} funds from master cache")
                        return cached_data['data']
        except:
            pass
    
    # Need to scrape all funds
    print("DEBUG: Master cache expired/missing, scraping all funds...")
    url = "https://www.finect.com/fondos-inversion/listado?company=77ab51c2,77ed42dd,76bfbad1,7860f2cb,77353b3c,785ffa11,78e9c382,77da1bc2,776f9ac2,786f2610,7735e497,76b95390,775ffb5d&order=-M12"
    
    # Scrape with many scrolls to get all 1000+ funds (~40 scrolls)
    all_funds = scrape_finect_selenium(url, limit=1200, category_id=None)
    
    if all_funds:
        # Save to master cache
        cache[cache_key] = {
            "timestamp": datetime.datetime.now().timestamp(),
            "data": all_funds
        }
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
        print(f"DEBUG: Saved {len(all_funds)} funds to master cache")
    
    return all_funds

def get_fund_ranking(category_name: str = "default", limit: int = 10) -> list:
    """
    Get top funds for a category from master cached fund list.
    Filters by category name from CATEGORY_FILTER_MAP.
    """
    try:
        # Get all funds from cache (or scrape if needed)
        all_funds = get_all_funds_cached()
        
        if not all_funds:
            print("DEBUG: No funds available")
            return []
        
        # Apply category filter
        filter_term = CATEGORY_FILTER_MAP.get(category_name.lower() if category_name else 'default', category_name)
        
        filtered_funds = all_funds
        if filter_term and filter_term != 'default' and filter_term is not None:
            search_lower = filter_term.lower()
            filtered = [f for f in all_funds if search_lower in f.get('category', '').lower()]
            if filtered:
                filtered_funds = filtered
                print(f"DEBUG: Filtered to {len(filtered)} funds by category: {filter_term}")
            else:
                print(f"DEBUG: No funds found for category {filter_term}, showing all")
        
        # Sort by 12M return (descending)
        filtered_funds.sort(key=lambda x: x.get('return1Y', 0), reverse=True)
        
        # Take top N and assign ranks
        ranking = filtered_funds[:limit]
        for i, fund in enumerate(ranking):
            fund['rank'] = i + 1
        
        return ranking
    
    except Exception as e:
        print(f"Error in get_fund_ranking: {e}")
        return []

def get_fallback_funds(category_name: str, limit: int = 10) -> list:
    """
    Returns empty list if scraping fails.
    Previously contained hardcoded data, now removed per user request.
    """
    return []
