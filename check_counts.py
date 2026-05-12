from sqlalchemy import create_engine, text
import os

engine = create_engine('mysql+pymysql://root:@localhost/driveguard_blackspots')

try:
    with engine.connect() as conn:
        user_id = 'demo-user-001'
        trips = conn.execute(text(f"SELECT id FROM trips WHERE vehicle_id IN (SELECT id FROM vehicles WHERE user_id = '{user_id}')")).fetchall()
        trip_ids = [t[0] for t in trips]
        print(f"Trips for {user_id}: {len(trip_ids)}")
        
        if trip_ids:
            points_count = conn.execute(text(f"SELECT count(*) FROM telemetry_points WHERE trip_id IN :tids"), {"tids": trip_ids}).scalar()
            print(f"Telemetry points for {user_id}: {points_count}")
        
        hotspots = conn.execute(text("SELECT count(*) FROM permanent_hotspots")).scalar()
        print(f"Global Hotspots: {hotspots}")
except Exception as e:
    import traceback
    traceback.print_exc()
