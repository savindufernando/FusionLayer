"""
Seed Permanent Hotspots for DriveGuard Map
Run: python seed_hotspots.py

Seeds the permanent_hotspots table with real accident-prone locations
in Sri Lanka so the mobile map has visible markers on first launch.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from api.database import SessionLocal, engine
from api.models import PermanentHotspot
from datetime import datetime, timezone


HOTSPOTS = [
    {"name": "Kaduwela Junction",        "lat": 6.9310, "lon": 79.9826, "count": 47, "boost": 0.6},
    {"name": "Kadawatha Interchange",    "lat": 7.0015, "lon": 79.9531, "count": 38, "boost": 0.5},
    {"name": "Maharagama Town",          "lat": 6.8481, "lon": 79.9281, "count": 35, "boost": 0.5},
    {"name": "Bambalapitiya Junction",   "lat": 6.8937, "lon": 79.8554, "count": 32, "boost": 0.4},
    {"name": "Nugegoda - High Level Rd", "lat": 6.8727, "lon": 79.8915, "count": 41, "boost": 0.5},
    {"name": "Piliyandala Junction",     "lat": 6.8008, "lon": 79.9258, "count": 29, "boost": 0.4},
    {"name": "Galle Road - Mt Lavinia",  "lat": 6.8381, "lon": 79.8660, "count": 26, "boost": 0.3},
    {"name": "Kelaniya Bridge",          "lat": 6.9554, "lon": 79.9229, "count": 44, "boost": 0.6},
    {"name": "Rajagiriya Flyover",       "lat": 6.9108, "lon": 79.8950, "count": 33, "boost": 0.4},
    {"name": "Dehiwala Junction",        "lat": 6.8558, "lon": 79.8637, "count": 30, "boost": 0.4},
    {"name": "Battaramulla Junction",    "lat": 6.9005, "lon": 79.9175, "count": 25, "boost": 0.3},
    {"name": "Kirulapone Canal Road",    "lat": 6.8789, "lon": 79.8741, "count": 22, "boost": 0.3},
    {"name": "Colombo Fort Station",     "lat": 6.9344, "lon": 79.8428, "count": 28, "boost": 0.4},
    {"name": "Pettah Market Area",       "lat": 6.9381, "lon": 79.8504, "count": 36, "boost": 0.5},
    {"name": "Borella Junction",         "lat": 6.9148, "lon": 79.8778, "count": 39, "boost": 0.5},
]


def ensure_table():
    """Ensure the permanent_hotspots table has all required columns."""
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT is_active FROM permanent_hotspots LIMIT 1"))
        except Exception:
            print("[INFO] Adding missing 'is_active' column...")
            try:
                conn.execute(text("ALTER TABLE permanent_hotspots ADD COLUMN is_active TINYINT(1) DEFAULT 1"))
                conn.commit()
                print("[OK] Column added.")
            except Exception as e2:
                print(f"[WARN] Could not add column: {e2}")


def seed():
    ensure_table()
    db = SessionLocal()

    try:
        existing = db.query(PermanentHotspot).count()
        if existing > 0:
            print(f"[INFO] {existing} hotspots already exist. Skipping seed.")
            return

        now = datetime.now(timezone.utc)
        for h in HOTSPOTS:
            spot = PermanentHotspot(
                name=h["name"],
                latitude=h["lat"],
                longitude=h["lon"],
                report_count=h["count"],
                risk_boost=h["boost"],
                first_reported=now,
                last_reported=now,
                is_active=True,
            )
            db.add(spot)

        db.commit()
        print(f"[OK] Seeded {len(HOTSPOTS)} permanent hotspots into the database.")
    except Exception as e:
        print(f"[ERROR] {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
