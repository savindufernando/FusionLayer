
import sys
import os
sys.path.append(os.getcwd())

from sqlalchemy import create_engine, text
from api.database import DATABASE_URL

engine = create_engine(DATABASE_URL)

with engine.connect() as connection:
    print("Columns in 'trips' table:")
    result = connection.execute(text("DESCRIBE trips"))
    for row in result:
        print(f"Field: {row[0]}, Type: {row[1]}, Null: {row[2]}, Key: {row[3]}, Default: {row[4]}, Extra: {row[5]}")
