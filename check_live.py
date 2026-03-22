import requests
import sys

def check_live_url():
    # The URL from your deployment log
    base_url = "https://asta-fl5z.onrender.com"
    
    print(f"Checking live deployment at: {base_url}")
    
    endpoints = [
        {"path": "/", "method": "HEAD"},
        {"path": "/health", "method": "HEAD"},
        {"path": "/health", "method": "GET"}
    ]
    
    for ep in endpoints:
        url = f"{base_url}{ep['path']}"
        try:
            if ep['method'] == "HEAD":
                resp = requests.head(url, timeout=5)
            else:
                resp = requests.get(url, timeout=5)
            
            print(f"[{ep['method']}] {ep['path']} -> {resp.status_code}")
            
            if resp.status_code != 200:
                print(f"   Response headers: {resp.headers}")
                print(f"   Response body: {resp.text[:200]}")
                
        except Exception as e:
            print(f"ERROR connecting to {url}: {e}")

if __name__ == "__main__":
    check_live_url()
