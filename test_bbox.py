import base64
import requests

# Create a dummy 640x480 white image in base64
from PIL import Image
import io

img = Image.new('RGB', (640, 480), color = 'white')
buffered = io.BytesIO()
img.save(buffered, format="JPEG")
img_str = base64.b64encode(buffered.getvalue()).decode()

response = requests.post(
    "http://localhost:8001/api/fused-predict/auto",
    json={
        "speed_kph": 50,
        "latitude": 6.9,
        "longitude": 79.8,
        "image_base64": img_str,
        "yolo_detections": []
    },
    headers={"X-API-Key": "dg-fusion-dev-key-2026"}
)

if response.status_code == 200:
    data = response.json()
    print("TSR Contribution:", data.get("tsr_contribution", {}))
else:
    print("Error:", response.status_code, response.text)
