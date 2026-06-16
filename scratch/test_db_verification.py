import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.database import SessionLocal
from api.models import User
from api.mobile_router import verify_password

db = SessionLocal()
try:
    email_clean = "savindunipun30@gmail.com".strip().lower()
    user = db.query(User).filter(User.email.ilike(email_clean)).first()
    print("Fetched User:", user.name if user else "None")
    if user:
        print("User Email in DB:", user.email)
        print("User ID:", user.id)
        print("User Password Hash:", user.password_hash)
        # Test verify password with '12345678'
        res = verify_password("12345678", user.password_hash)
        print("Verification result for '12345678':", res)
finally:
    db.close()
