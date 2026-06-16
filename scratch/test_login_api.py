import requests
import json

url = "http://localhost:8002/api/mobile/auth/login"
payload = {
    "email": "savindunipun30@gmail.com",
    "password": "12345678"
}
headers = {
    "Content-Type": "application/json"
}

try:
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    print("Status Code:", response.status_code)
    print("Response Body:", response.text)
except Exception as e:
    print("Request failed:", e)
