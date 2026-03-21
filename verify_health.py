import requests
import time
import subprocess
import sys
import threading

def run_server():
    subprocess.run([sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8008"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

base_url = "http://127.0.0.1:8008"

def test_endpoints():
    print("Waiting for server to start...")
    time.sleep(5)  # Give time for uvicorn to start

    endpoints = [
        {"path": "/", "methods": ["GET", "HEAD"]},
        {"path": "/health", "methods": ["GET", "HEAD"]},
        {"path": "/api/health", "methods": ["GET"]}, # HEAD not explicitly added to api/health but user primarily cared about main /health
        {"path": "/debug/routes", "methods": ["GET"]}
    ]

    failed = False
    for ep in endpoints:
        path = ep["path"]
        url = base_url + path
        for method in ep["methods"]:
            try:
                if method == "GET":
                    response = requests.get(url, timeout=2)
                elif method == "HEAD":
                    response = requests.head(url, timeout=2)
                
                print(f"[{method}] {path} -> {response.status_code}")
                if response.status_code != 200:
                    print(f"ERROR: {method} {path} returned {response.status_code}")
                    failed = True
                
                if method == "GET" and path == "/health":
                    json_resp = response.json()
                    if json_resp.get("status") != "ok":
                         print(f"ERROR: Unexpected response body for /health: {json_resp}")
                         failed = True

            except Exception as e:
                print(f"ERROR: Failed to connect to {url}: {e}")
                failed = True

    if failed:
        sys.exit(1)
    else:
        print("All checks passed!")
        sys.exit(0)

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    test_endpoints()
