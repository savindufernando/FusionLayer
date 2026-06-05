import base64
import httpx
import json
import yaml
from pathlib import Path
from PIL import Image, ImageDraw
import io

def create_test_frame():
    img = Image.new('RGB', (640, 480), (100, 150, 100))
    draw = ImageDraw.Draw(img)
    draw.ellipse([450, 80, 530, 160], fill=(220, 30, 30), outline=(200, 20, 20))
    draw.rectangle([80, 100, 150, 170], fill=(30, 60, 200))
    draw.polygon([(300, 80), (340, 120), (300, 160), (260, 120)], fill=(240, 200, 30))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85)
    return base64.b64encode(buf.getvalue()).decode()

frame_b64 = create_test_frame()

print("--- 1. Reading Fusion config.yaml ---")
config_path = Path("config.yaml")
if config_path.exists():
    with open(config_path) as f:
        print(f.read())
else:
    print("config.yaml not found at", config_path.resolve())

print("\n--- 2. Circuit Breaker Status ---")
try:
    r = httpx.get("http://localhost:8002/api/fusion/circuit-status")
    print("Circuit Status:", r.status_code)
    print(json.dumps(r.json(), indent=2))
except Exception as e:
    print("Circuit Status Fetch Error:", e)

print("\n--- 3. Direct TSR Predict (base64) ---")
try:
    r = httpx.post(
        "http://localhost:8001/api/predict/base64",
        json={"image": frame_b64},
        headers={"X-API-Key": "dg-fusion-dev-key-2026"},
        timeout=15.0
    )
    print("TSR Status:", r.status_code)
    print("TSR Response:", json.dumps(r.json(), indent=2))
except Exception as e:
    print("TSR Direct Error:", e)

print("\n--- 4. Fusion Layer Auto-Predict ---")
try:
    r = httpx.post(
        "http://localhost:8002/api/fused-predict/auto",
        json={
            "latitude": 6.9147,
            "longitude": 79.8775,
            "heading": 45.0,
            "speed_kph": 40.0,
            "scenario": "realtime",
            "image_base64": frame_b64
        },
        headers={"X-API-Key": "dg-fusion-dev-key-2026"},
        timeout=15.0
    )
    print("Fusion Status:", r.status_code)
    print("Fusion Response:", json.dumps(r.json(), indent=2))
except Exception as e:
    print("Fusion Auto-Predict Error:", e)
