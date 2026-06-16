import requests

url = "https://driveguard-api.loca.lt/"
try:
    response = requests.get(url, timeout=5)
    print("Status Code:", response.status_code)
    print("Headers:", dict(response.headers))
    print("Body:", response.text[:200])
except Exception as e:
    print("Failed to connect:", e)
