
import sys
import os
sys.path.append(os.getcwd())

from sqlalchemy import create_engine, text, inspect
from api.database import DATABASE_URL

engine = create_engine(DATABASE_URL)
inspector = inspect(engine)

tables = inspector.get_table_names()
for table_name in tables:
    print(f"\nTable: {table_name}")
    columns = inspector.get_columns(table_name)
    for column in columns:
        print(f"  Column: {column['name']}, Type: {column['type']}")
