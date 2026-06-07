import requests
from bs4 import BeautifulSoup
import csv
import time
import re
import random

def scrape_jpx400():
    # Base URL with placeholder for page number
    base_url = "https://kabutan.jp/themes/?theme=JPX%E6%97%A5%E7%B5%8C400&market=0&capitalization=-1&dispmode=normal&stc=&stm=0&page={}"
    stocks = {} # Use dict to dedup automatically
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
    }
    
    print("Scraping JPX-Nikkei 400 constituents...")
    
    # 27 pages expected for ~400 items (15 per page)
    for page in range(1, 40):
        url = base_url.format(page)
        print(f"Fetching page {page}...")
        
        try:
            resp = requests.get(url, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Find the main table. Usually it's the one with specific classes or just look for links.
            # On Kabutan theme page:
            # <tr>
            #   <td class="tac"><a href="/stock/?code=XXXX">XXXX</a></td>
            #   <td><a href="/stock/?code=XXXX">NAME</a></td> ...
            
            # Find all links that look like stock codes
            # The structure is usually Code Link inside a TD, then Name Link inside next TD
            
            # Let's find table rows first to be safe
            rows = soup.find_all('tr')
            found_on_page = 0
            
            for tr in rows:
                tds = tr.find_all('td')
                if not tds:
                    continue
                    
                # Check 1st column for code link
                code_link = tds[0].find('a', href=re.compile(r'/stock/\?code=\d{4}'))
                if code_link:
                    code_text = code_link.text.strip()
                    # Verify it looks like a code (4 digits)
                    if re.match(r'^\d{4}$', code_text):
                        # Name is usually in the 2nd column
                        name_text = "Unknown"
                        if len(tds) > 1:
                            name_link = tds[1].find('a')
                            if name_link:
                                name_text = name_link.text.strip()
                            else:
                                name_text = tds[1].text.strip()
                        
                        stocks[code_text] = name_text
                        found_on_page += 1
            
            print(f"  Found {found_on_page} stocks on page {page}")
            
            if found_on_page == 0:
                # Double check if we are blocked or just empty
                # If page 1 has 0, something is wrong. If page 30 has 0, we are done.
                if page == 1:
                    print("  Warning: No stocks found on page 1. Check selector.")
                    # Fallback: print part of HTML to debug
                    # print(soup.prettify()[:1000])
                    break
                else:
                    print("  No more stocks found. Stopping.")
                    break
            
            time.sleep(random.uniform(1.0, 3.0)) # Be polite
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print("  Page not found (404). Stopping.")
                break
            print(f"Error on page {page}: {e}")
            break
        except Exception as e:
            print(f"Error on page {page}: {e}")
            break
            
    print(f"Total unique stocks found: {len(stocks)}")
    
    # Save to CSV
    if stocks:
        with open('data/nikkei400.csv', 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['symbol', 'name'])
            for code, name in stocks.items():
                writer.writerow([code, name])
        print("Saved to data/nikkei400.csv")
    else:
        print("No stocks to save.")

if __name__ == "__main__":
    scrape_jpx400()
