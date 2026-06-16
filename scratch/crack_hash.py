import hashlib

candidates = [
    "password", "password123", "12345678", "admin", "admin123", "savindu", "savindu123", "Savindu@123", "savindunipun30"
]
target = "ef797c8118f02dfb649607dd5d3f8c7623048c9c063d532cc95c5ed7a898a64f"

for c in candidates:
    h = hashlib.sha256(c.encode()).hexdigest()
    if h == target:
        print(f"Matched! Password is: '{c}'")
        break
else:
    print("No match found in candidate list.")
