"""
Database configuration for DriveGuard Cloud API.
Connects to XAMPP MySQL (driveguard_blackspots database).
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ── XAMPP MySQL Connection ────────────────────────────────────────────────
# Default XAMPP: root user, no password, port 3306
# Change these if your XAMPP setup differs.
MYSQL_USER = "root"
MYSQL_PASSWORD = ""           # XAMPP default — no password
MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_DB = "driveguard_blackspots"

DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,        # Auto-reconnect if MySQL restarts
    echo=False,                 # Set True to see SQL queries in console
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency for FastAPI endpoints to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all database tables that don't already exist."""
    from . import models  # noqa: F401 — import to register models
    Base.metadata.create_all(bind=engine)
