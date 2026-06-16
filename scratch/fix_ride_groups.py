import sys
import os
sys.path.append(os.getcwd())

from sqlalchemy import create_engine, text
from api.database import DATABASE_URL

engine = create_engine(DATABASE_URL)

with engine.connect() as connection:
    print("Describing 'ride_groups' table before modification:")
    try:
        result = connection.execute(text("DESCRIBE ride_groups"))
        columns = [row[0] for row in result]
        print(f"Current columns: {columns}")
        
        if "creator_id" not in columns:
            print("Adding 'creator_id' column to 'ride_groups' table...")
            # Add column
            connection.execute(text("ALTER TABLE ride_groups ADD COLUMN creator_id VARCHAR(36) NULL"))
            print("Added column 'creator_id'")
            
            # Add foreign key constraint
            try:
                connection.execute(text(
                    "ALTER TABLE ride_groups ADD CONSTRAINT fk_ride_groups_creator "
                    "FOREIGN KEY (creator_id) REFERENCES users(id) ON DELETE SET NULL"
                ))
                print("Added foreign key constraint referencing users(id)")
            except Exception as e_fk:
                print(f"Warning: Could not add foreign key constraint: {e_fk}")
                
            connection.commit()
            print("Migration completed successfully!")
        else:
            print("'creator_id' column already exists in 'ride_groups' table.")
            
    except Exception as e:
        print(f"Error during migration: {e}")
        
    print("Done.")
