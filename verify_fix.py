import requests
import time
import subprocess
import sys
import threading
import os

def run_server():
    # Force flushing of stdout/stderr
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    subprocess.run([sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8009"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, env=env)

base_url = "http://127.0.0.1:8009"

def verify_endpoints():
    print("Waiting for server to start...")
    time.sleep(5)  # Give time for uvicorn to start

    endpoints = [
        {"path": "/health", "methods": ["HEAD", "GET"]},
        {"path": "/debug/routes", "methods": ["GET"]},
        {"path": "/api/health", "methods": ["GET"]},
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
                    print(f"FAILED: Expected 200 but got {response.status_code} for {method} {path}")
                    failed = True
            except requests.exceptions.RequestException as e:
                print(f"ERROR: Could not connect to {url}: {e}")
                failed = True

    if failed:
        print("Verification FAILED.")
        sys.exit(1)
    else:
        print("Verification PASSED.")
        sys.exit(0)

if __name__ == "__main__":
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    verify_endpoints()
