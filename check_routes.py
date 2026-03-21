import requests, sys, time

def check(url):
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            print(f"{url} -> OK ({resp.json()})")
            return True
        else:
            print(f"{url} -> FAILED ({resp.status_code})")
            return False
    except Exception as e:
        print(f"{url} -> EXCEPTION: {str(e)}")
        return False

print("Waiting for server startup...")
time.sleep(5) 

print("\n--- FINAL HEALTH CHECK ---")
ok1 = check("http://localhost:8002/")
ok2 = check("http://localhost:8002/health")
ok3 = check("http://localhost:8002/api/health") # New check
ok4 = check("http://localhost:8002/api/test")
print("--------------------------\n")
