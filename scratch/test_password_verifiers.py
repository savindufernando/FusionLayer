import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.mobile_router import verify_password, get_password_hash

# Test 1: bcrypt matching
bcrypt_hash = get_password_hash("mysecretpassword")
print("Bcrypt Match:", verify_password("mysecretpassword", bcrypt_hash))
print("Bcrypt Mismatch:", verify_password("wrongpassword", bcrypt_hash))

# Test 2: SHA-256 matching (fallback)
# '12345678' -> 'ef797c8118f02dfb649607dd5d3f8c7623048c9c063d532cc95c5ed7a898a64f'
sha256_hash = "ef797c8118f02dfb649607dd5d3f8c7623048c9c063d532cc95c5ed7a898a64f"
print("SHA256 Match:", verify_password("12345678", sha256_hash))
print("SHA256 Mismatch:", verify_password("wrongpassword", sha256_hash))
