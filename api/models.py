"""
SQLAlchemy ORM Models for the DriveGuard Cloud API.

Implements the User → Vehicle → Trip → TelemetryPoint hierarchy
designed in the IoT Architecture document.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Float, Boolean, Integer,
    DateTime, ForeignKey, Text, JSON
)
from sqlalchemy.orm import relationship

from .database import Base


def generate_uuid():
    return str(uuid.uuid4())


# ─── User ─────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    vehicles = relationship("Vehicle", back_populates="owner", cascade="all, delete-orphan")


# ─── Vehicle ──────────────────────────────────────────────────────────────

class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    make_model = Column(String(255), nullable=False)              # e.g., "Toyota Aqua"
    vehicle_type = Column(String(50), default="Car")              # Car, Motorcycle, Van
    led_stick_mac = Column(String(17), nullable=True)             # BLE MAC address
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    owner = relationship("User", back_populates="vehicles")
    trips = relationship("Trip", back_populates="vehicle", cascade="all, delete-orphan")


# ─── Trip ─────────────────────────────────────────────────────────────────

class Trip(Base):
    __tablename__ = "trips"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    vehicle_id = Column(String(36), ForeignKey("vehicles.id"), nullable=False)
    start_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    end_time = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    # Aggregated stats (updated as telemetry flows in)
    avg_risk_score = Column(Float, default=0.0)
    max_risk_score = Column(Float, default=0.0)
    total_distance_km = Column(Float, default=0.0)
    red_alert_count = Column(Integer, default=0)
    yellow_alert_count = Column(Integer, default=0)
    point_count = Column(Integer, default=0)

    # Relationships
    vehicle = relationship("Vehicle", back_populates="trips")
    telemetry_points = relationship("TelemetryPoint", back_populates="trip", cascade="all, delete-orphan")


# ─── Telemetry Point ─────────────────────────────────────────────────────

class TelemetryPoint(Base):
    __tablename__ = "telemetry_points"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(String(36), ForeignKey("trips.id"), nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # GPS data
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    speed_kph = Column(Float, default=0.0)
    heading = Column(Float, default=0.0)

    # Risk assessment (from Fusion Engine)
    risk_score = Column(Float, default=0.0)
    risk_level = Column(String(10), default="LOW")  # LOW, MEDIUM, HIGH
    alert_level = Column(String(10), default="GREEN")  # GREEN, YELLOW, RED

    # Detected signs (stored as JSON array)
    detected_signs = Column(JSON, nullable=True)

    # DS theory metrics
    belief_dangerous = Column(Float, default=0.0)
    conflict_measure = Column(Float, default=0.0)

    # Relationships
    trip = relationship("Trip", back_populates="telemetry_points")


# ─── Crowdsourced Sign Map (TSR Virtualization) ──────────────────────────

class CrowdsourcedSign(Base):
    __tablename__ = "crowdsourced_signs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    class_id = Column(Integer, nullable=False)
    class_name = Column(String(100), nullable=False)
    confidence = Column(Float, default=0.0)
    report_count = Column(Integer, default=1)          # How many users confirmed this sign
    first_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Blackspot Reports (System 1: Crowdsourced Hazard Markers) ───────────

class BlackspotReport(Base):
    __tablename__ = "blackspot_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    report_type = Column(String(50), default="hazard")  # hazard, accident, roadblock
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True)         # Auto-expire after ~2 hours


# ─── Insurance Claims (System 2: Official Accident Reporting) ────────────

class InsuranceClaim(Base):
    __tablename__ = "insurance_claims"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    vehicle_id = Column(String(36), ForeignKey("vehicles.id"), nullable=False)
    trip_id = Column(String(36), ForeignKey("trips.id"), nullable=True)

    # Crash location
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    # Pre-crash telemetry snapshot
    pre_crash_speed_kph = Column(Float, nullable=True)
    pre_crash_risk_score = Column(Float, nullable=True)
    weather_condition = Column(String(50), nullable=True)

    # User-submitted data (from smartphone handoff)
    statement = Column(Text, nullable=True)
    photo_urls = Column(JSON, nullable=True)      # List of cloud storage URLs

    # Status tracking
    status = Column(String(50), default="DRAFT")  # DRAFT, SUBMITTED, PROCESSING, SETTLED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    submitted_at = Column(DateTime, nullable=True)


# ─── Accident Reports (Police Reporting) ─────────────────────────────────

class AccidentReport(Base):
    __tablename__ = "accident_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    severity = Column(String(50), default="MINOR")       # MINOR, MODERATE, SEVERE, FATAL
    description = Column(Text, nullable=True)
    vehicles_involved = Column(Integer, default=1)
    injuries = Column(Integer, default=0)
    police_notified = Column(Boolean, default=False)
    status = Column(String(50), default="REPORTED")       # REPORTED, INVESTIGATING, CLOSED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Permanent Hotspots (from DZ Prediction) ─────────────────────────────

class PermanentHotspot(Base):
    __tablename__ = "permanent_hotspots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    report_count = Column(Integer, default=0)
    risk_boost = Column(Float, default=0.0)
    first_reported = Column(DateTime, nullable=True)
    last_reported = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
