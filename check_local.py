import requests, sys, time

def check(url):
    try:
        resp = requests.get(url, timeout=5)
        print(f"{url} -> {resp.status_code} {resp.json()}")
        return True
    except Exception as e:
        print(f"{url} -> FAILED: {str(e)}")
        return False

print("Waiting for server...")
time.sleep(5) 

print("\n--- HEALTH CHECKS ---")
check("http://localhost:8001/")
check("http://localhost:8001/health")
check("http://localhost:8001/api/test")
print("---------------------\n")
