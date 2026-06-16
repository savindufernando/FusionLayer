with open("api/mobile_router.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "/login" in line or "/register" in line or "def login" in line or "def register" in line or "password_hash" in line:
        print(f"Line {i+1}: {line.strip()}")
