import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.database import SessionLocal
from api.models import PermanentHotspot

db = SessionLocal()
try:
    hotspots = db.query(PermanentHotspot).all()
    print(f"Total hotspots in database: {len(hotspots)}")
    for h in hotspots:
        print(f"ID: {h.id}, Name: {h.name}, Lat: {h.latitude}, Lon: {h.longitude}, Active: {h.is_active}")
finally:
    db.close()
