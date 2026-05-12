
import sys
import os
sys.path.append(os.getcwd())

from sqlalchemy import create_engine, text
from api.database import DATABASE_URL

engine = create_engine(DATABASE_URL)

with engine.connect() as connection:
    print("Adding missing columns to 'trips' table...")
    try:
        connection.execute(text("ALTER TABLE trips ADD COLUMN hard_brake_count INTEGER DEFAULT 0"))
        print("Added 'hard_brake_count'")
    except Exception as e:
        print(f"Error adding 'hard_brake_count': {e}")

    try:
        connection.execute(text("ALTER TABLE trips ADD COLUMN harsh_corner_count INTEGER DEFAULT 0"))
        print("Added 'harsh_corner_count'")
    except Exception as e:
        print(f"Error adding 'harsh_corner_count': {e}")

    try:
        connection.execute(text("ALTER TABLE trips ADD COLUMN safety_score FLOAT DEFAULT 100.0"))
        print("Added 'safety_score'")
    except Exception as e:
        print(f"Error adding 'safety_score': {e}")
    
    connection.commit()
    print("Done.")
