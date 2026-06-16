import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.database import SessionLocal
from api.models import User

db = SessionLocal()
try:
    users = db.query(User).all()
    print("Total users in database:", len(users))
    for u in users:
         print(f"ID: {u.id}, Name: {u.name}, Email: {u.email}, Password Hash: {u.password_hash}")
finally:
    db.close()
