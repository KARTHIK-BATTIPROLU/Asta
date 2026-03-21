import asyncio
import httpx
import time
from collections import defaultdict
from typing import Dict, Any

# CONFIGURATION
# ------------------------------------------------------------------------------
# REPLACE THIS WITH YOUR ACTUAL RENDER APP URL
BASE_URL = "https://your-app.onrender.com" 
# ------------------------------------------------------------------------------

ENDPOINTS = [
    "/",
    "/health",
    "/api/health",
    "/api/test"
]

TOTAL_REQUESTS = 100
BATCH_SIZE = 10
TIMEOUT = 10.0
RETRIES = 2

# METRICS STORAGE
results: Dict[str, Dict[str, int]] = defaultdict(lambda: {"success": 0, "fail": 0, "404": 0, "timeout": 0, "connection": 0, "other": 0})
failed_endpoints = set()

async def fetch(client: httpx.AsyncClient, endpoint: str, attempt: int = 1):
    """
    Fetches a single endpoint with retry logic.
    """
    url = f"{BASE_URL}{endpoint}"
    
    try:
        response = await client.get(url, timeout=TIMEOUT)
        
        if response.status_code == 200:
            return "success", response.status_code
        elif response.status_code == 404:
            return "404", response.status_code
        else:
            return "fail", response.status_code

    except httpx.TimeoutException:
        if attempt <= RETRIES:
            # print(f"Timeout on {endpoint} (Attempt {attempt}). Retrying...")
            return await fetch(client, endpoint, attempt + 1)
        return "timeout", 0
        
    except (httpx.ConnectError, httpx.NetworkError):
        if attempt <= RETRIES:
            # print(f"Connection error on {endpoint} (Attempt {attempt}). Retrying...")
            return await fetch(client, endpoint, attempt + 1)
        return "connection", 0
        
    except Exception as e:
        return "other", 0

async def run_batch(endpoint: str, count: int):
    """
    Runs a batch of requests for a specific endpoint.
    """
    async with httpx.AsyncClient() as client:
        tasks = []
        for _ in range(count):
            tasks.append(fetch(client, endpoint))
        
        batch_results = await asyncio.gather(*tasks)
        
        for res, code in batch_results:
            if res == "success":
                results[endpoint]["success"] += 1
            elif res == "404":
                results[endpoint]["404"] += 1
                results[endpoint]["fail"] += 1
            elif res == "timeout":
                results[endpoint]["timeout"] += 1
                results[endpoint]["fail"] += 1
            elif res == "connection":
                results[endpoint]["connection"] += 1
                results[endpoint]["fail"] += 1
            else:
                results[endpoint]["other"] += 1
                results[endpoint]["fail"] += 1
                
            if res != "success":
                # Detailed log for failures
                error_msg = res.upper()
                if res == "fail": error_msg = f"STATUS {code}"
                # print(f"[FAIL] {endpoint} -> {error_msg}")

async def main():
    print(f"\n🚀 STARTING STABILITY TEST")
    print(f"Target: {BASE_URL}")
    print(f"Config: {TOTAL_REQUESTS} reqs/endpoint | Batch: {BATCH_SIZE} | Retries: {RETRIES}\n")

    start_time = time.time()

    for endpoint in ENDPOINTS:
        print(f"Testing {endpoint}...", end="", flush=True)
        
        # Process in batches
        remaining = TOTAL_REQUESTS
        while remaining > 0:
            current_batch = min(remaining, BATCH_SIZE)
            await run_batch(endpoint, current_batch)
            remaining -= current_batch
            print(".", end="", flush=True)
            
        print(" Done.")

    duration = time.time() - start_time
    
    # REPORT GENERATION
    print("\n" + "="*60)
    print(f"{'FINAL TEST REPORT':^60}")
    print("="*60)
    print(f"{'ENDPOINT':<20} | {'REQS':<5} | {'SUCCESS':<8} | {'FAIL':<5} | {'RATE %':<8}")
    print("-" * 60)

    for endpoint in ENDPOINTS:
        stats = results[endpoint]
        total = TOTAL_REQUESTS
        success = stats["success"]
        fails = stats["fail"]
        rate = (success / total) * 100
        
        print(f"{endpoint:<20} | {total:<5} | {success:<8} | {fails:<5} | {rate:<7.1f}%")
        
        if rate < 100:
            failed_endpoints.add(endpoint)

    print("-" * 60)
    
    if failed_endpoints:
        print("\n⚠️  ISSUES DETECTED:")
        for ep in failed_endpoints:
            stats = results[ep]
            details = []
            if stats["404"] > 0: details.append(f"404 Not Found: {stats['404']}")
            if stats["timeout"] > 0: details.append(f"Timeouts: {stats['timeout']}")
            if stats["connection"] > 0: details.append(f"Connection Errors: {stats['connection']}")
            if stats["other"] > 0: details.append(f"Other Errors: {stats['other']}")
            
            print(f"  ❌ {ep}: {', '.join(details)}")
    else:
        print("\n✅ ALL SYSTEMS GO! No failures detected.")

    print(f"\nTest completed in {duration:.2f} seconds.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest cancelled by user.")
