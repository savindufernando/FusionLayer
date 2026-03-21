import asyncio
import time
import httpx
import math
import random
from typing import List, Tuple

BASE_URL = "http://localhost:8002"
MOBILE_ANALYZE_ENDPOINT = "/api/mobile/analyze"

def add_jitter(lat: float, lon: float, meters: float = 5.0) -> Tuple[float, float]:
    """Add random jitter to GPS coordinates."""
    # Rough estimate: 1 degree latitude = 111,000 meters
    lat_jitter = (random.uniform(-1, 1) * meters) / 111000.0
    lon_jitter = (random.uniform(-1, 1) * meters) / (111000.0 * math.cos(math.radians(lat)))
    return lat + lat_jitter, lon + lon_jitter

async def simulate_trip(scenario: str = "baseline"):
    # Borella Junction is roughly at (6.9147, 79.8775)
    # Start south of Borella and go north through it
    start_lat, start_lon = 6.9100, 79.8775
    end_lat, end_lon = 6.9200, 79.8775
    steps = 15

    
    print(f"Simulating Trip: Scenario={scenario}")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for i in range(steps):
            # Interpolate position
            t = i / steps
            lat = start_lat + (end_lat - start_lat) * t
            lon = start_lon + (end_lon - start_lon) * t
            
            payload_lat, payload_lon = lat, lon
            if scenario == "jitter":
                payload_lat, payload_lon = add_jitter(lat, lon, meters=10.0)
            
            payload = {
                "user_id": "sim_user",
                "vehicle_id": "sim_car",
                "latitude": payload_lat,
                "longitude": payload_lon,
                "heading": 45.0,
                "speed_kph": 40.0,
            }
            
            try:
                start_time = time.perf_counter()
                resp = await client.post(f"{BASE_URL}{MOBILE_ANALYZE_ENDPOINT}", json=payload)
                resp.raise_for_status()
                data = resp.json()
                latency = (time.perf_counter() - start_time) * 1000
                
                print(f"Step {i+1:02d}: Lat={payload_lat:.6f}, Lon={payload_lon:.6f} | "
                      f"Risk={data['risk_score']:.1f} ({data['risk_level']}) | "
                      f"Alert={data['alert_level']} | Latency={latency:.1f}ms")
                
                if data['risk_level'] != "LOW":
                    print(f"  >>> ALERT: {data['fusion_reasons']}")
                
            except Exception as e:
                print(f"Step {i+1:02d}: FAILED - {e}")
            
            # Wait 1s between steps to simulate real-time movement
            await asyncio.sleep(1.0)

if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    asyncio.run(simulate_trip(mode))
