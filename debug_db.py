import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pathlib import Path

# Load env
load_dotenv(Path(__file__).parent / ".env")

MYSQL_USER = "root"
MYSQL_PASSWORD = ""
MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_DB = "driveguard_blackspots"

DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    print("--- Database Debug Summary ---")
    
    # 1. Check User
    user = conn.execute(text("SELECT id, name FROM users WHERE id='demo-user-001'")).fetchone()
    print(f"User: {user}")
    
    # 2. Check Vehicles
    vehicles = conn.execute(text("SELECT id, make_model FROM vehicles WHERE user_id='demo-user-001'")).fetchall()
    print(f"Vehicles: {vehicles}")
    v_ids = [v[0] for v in vehicles]
    
    if v_ids:
        v_placeholders = ",".join([f"'{vid}'" for vid in v_ids])
        
        # 3. Check Trips
        trips = conn.execute(text(f"SELECT id, avg_risk_score, point_count FROM trips WHERE vehicle_id IN ({v_placeholders})")).fetchall()
        print(f"Trips ({len(trips)}): {trips}")
        t_ids = [t[0] for t in trips]
        
        if t_ids:
            t_placeholders = ",".join([f"'{tid}'" for tid in t_ids])
            
            # 4. Check Telemetry Points
            points_count = conn.execute(text(f"SELECT COUNT(*) FROM telemetry_points WHERE trip_id IN ({t_placeholders})")).scalar()
            print(f"Total Telemetry Points: {points_count}")
            
            risky_points = conn.execute(text(f"SELECT COUNT(*) FROM telemetry_points WHERE trip_id IN ({t_placeholders}) AND risk_score > 30")).scalar()
            print(f"Risky Points (>30): {risky_points}")
            
            if risky_points > 0:
                sample = conn.execute(text(f"SELECT latitude, longitude, risk_score FROM telemetry_points WHERE trip_id IN ({t_placeholders}) AND risk_score > 30 LIMIT 5")).fetchall()
                print(f"Sample Risky Points: {sample}")
            else:
                max_risk = conn.execute(text(f"SELECT MAX(risk_score) FROM telemetry_points WHERE trip_id IN ({t_placeholders})")).scalar()
                print(f"Max Risk Score found in DB: {max_risk}")
    else:
        print("No vehicles found for this user.")
