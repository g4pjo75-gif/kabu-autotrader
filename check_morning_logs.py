import os
import glob

def check_logs():
    files = glob.glob(r"d:\ainigravity\work\kabu\antigravity\logs\app.log*")
    
    last_log = None
    for filename in sorted(files):
        with open(filename, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "2026-03-18" in line:
                    if "09:" in line or "10:" in line or "11:" in line:
                        if not last_log:
                            print("Found morning logs:")
                            print(line.strip())
                        last_log = line.strip()

    if last_log:
        print("Last morning log:")
        print(last_log)
    else:
        print("No logs found for 09:00 - 11:59 today.")

if __name__ == "__main__":
    check_logs()
