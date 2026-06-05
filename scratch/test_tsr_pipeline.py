"""
Debug script: captures a frame from a dashcam video, sends it through TSR,
and prints the full response chain.
"""
import base64
import httpx
import json
import sys
from pathlib import Path

# Create a simple test image with colored shapes (simulates a sign)
from PIL import Image, ImageDraw
import io

def create_test_frame():
    """Create a 640x480 test frame with a red circle (simulated stop sign)."""
    img = Image.new('RGB', (640, 480), (100, 150, 100))  # Greenish background
    draw = ImageDraw.Draw(img)
    # Red octagon-ish circle in upper-right area (simulating a stop sign)
    draw.ellipse([450, 80, 530, 160], fill=(220, 30, 30), outline=(200, 20, 20))
    # Blue rectangle in left area (simulating an info sign)
    draw.rectangle([80, 100, 150, 170], fill=(30, 60, 200))
    # Yellow diamond in center (simulating a warning sign)
    draw.polygon([(300, 80), (340, 120), (300, 160), (260, 120)], fill=(240, 200, 30))
    
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85)
    return base64.b64encode(buf.getvalue()).decode()

# Step 1: Test TSR directly
print("=" * 60)
print("STEP 1: Direct TSR Backend Test (/api/predict/base64)")
print("=" * 60)

frame_b64 = create_test_frame()
print(f"Frame size: {len(frame_b64)} bytes base64")

try:
    r = httpx.post(
        "http://localhost:8001/api/predict/base64",
        json={"image": frame_b64},
        headers={"X-API-Key": "dg-fusion-dev-key-2026"},
        timeout=15.0
    )
    print(f"TSR Status: {r.status_code}")
    data = r.json()
    print(f"TSR Response: {json.dumps(data, indent=2)}")
except Exception as e:
    print(f"TSR ERROR: {e}")

# Step 2: Test through Fusion Layer
print("\n" + "=" * 60)
print("STEP 2: Full Fusion Pipeline (/api/fused-predict/auto)")
print("=" * 60)

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
    print(f"Fusion Status: {r.status_code}")
    data = r.json()
    print(f"TSR Contribution: {json.dumps(data.get('tsr_contribution', {}), indent=2)}")
    print(f"Active Signs: {json.dumps(data.get('active_signs', []), indent=2)}")
    print(f"Fused Risk: {data.get('fused_risk_score')} ({data.get('fused_risk_level')})")
except Exception as e:
    print(f"Fusion ERROR: {e}")
