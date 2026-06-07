import os
import glob

def check_logs():
    files = glob.glob(r"d:\ainigravity\work\kabu\antigravity\logs\app.log*")
    
    trade_keywords = ["[TRADE]", " BUY ", " SELL ", "Trade execution"]
    
    found_any = False
    for filename in files:
        with open(filename, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "2026-03-18" in line:
                    for kw in trade_keywords:
                        if kw in line:
                            print(line.strip())
                            found_any = True
                            break
                            
    if not found_any:
        print("No trade keywords found for 2026-03-18.")

if __name__ == "__main__":
    check_logs()
