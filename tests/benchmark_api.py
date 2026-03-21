import asyncio
import time
import httpx
import statistics
from typing import List, Dict

# Configuration
BASE_URL = "http://localhost:8002"
MOBILE_ANALYZE_ENDPOINT = "/api/mobile/analyze"
API_KEY = "test_key"  # Adjust if needed

async def benchmark_single_request(client: httpx.AsyncClient, payload: Dict) -> float:
    start_time = time.perf_counter()
    try:
        response = await client.post(
            f"{BASE_URL}{MOBILE_ANALYZE_ENDPOINT}",
            json=payload,
            headers={"x-api-key": API_KEY, "bypass-tunnel-reminder": "true"}
        )
        response.raise_for_status()
        end_time = time.perf_counter()
        return end_time - start_time
    except Exception as e:
        print(f"Request failed: {e}")
        return -1.0

async def run_benchmark(num_requests: int = 50, concurrency: int = 1):
    payload = {
        "user_id": "benchmarker",
        "vehicle_id": "bench_car",
        "latitude": 6.9271,
        "longitude": 79.8612,
        "heading": 90.0,
        "speed_kph": 60.0,
        "scenario": "auto"
    }
    
    # Optional: include a dummy base64 image to test TSR path
    # payload["image_base64"] = "..." 

    print(f"Starting benchmark: {num_requests} requests, concurrency={concurrency}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        latencies = []
        if concurrency == 1:
            for i in range(num_requests):
                latency = await benchmark_single_request(client, payload)
                if latency > 0:
                    latencies.append(latency)
                if (i + 1) % 10 == 0:
                    print(f"Progress: {i + 1}/{num_requests}")
        else:
            # Batch concurrent requests
            for i in range(0, num_requests, concurrency):
                tasks = [benchmark_single_request(client, payload) for _ in range(min(concurrency, num_requests - i))]
                results = await asyncio.gather(*tasks)
                latencies.extend([r for r in results if r > 0])
                print(f"Progress: {min(i + concurrency, num_requests)}/{num_requests}")

    if not latencies:
        print("Error: No successful requests recorded.")
        return

    # Convert to milliseconds
    latencies_ms = [l * 1000 for l in latencies]
    
    print("\n--- Benchmark Results ---")
    print(f"Successful Requests: {len(latencies_ms)}/{num_requests}")
    print(f"Meant Latency: {statistics.mean(latencies_ms):.2f} ms")
    print(f"Median Latency: {statistics.median(latencies_ms):.2f} ms")
    print(f"Min Latency: {min(latencies_ms):.2f} ms")
    print(f"Max Latency: {max(latencies_ms):.2f} ms")
    print(f"P95 Latency: {statistics.quantiles(latencies_ms, n=20)[18]:.2f} ms")
    print(f"P99 Latency: {statistics.quantiles(latencies_ms, n=100)[98]:.2f} ms")
    print("--------------------------\n")

if __name__ == "__main__":
    asyncio.run(run_benchmark(num_requests=50, concurrency=1))
