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

    # Social / Gamification fields
    avatar_color = Column(String(7), default="#00E676")
    bio = Column(String(255), default="")
    safety_score = Column(Float, default=100.0)
    total_trips = Column(Integer, default=0)
    total_distance_km = Column(Float, default=0.0)
    xp_points = Column(Integer, default=0)
    driver_level = Column(Integer, default=1)

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
    hard_brake_count = Column(Integer, default=0)
    harsh_corner_count = Column(Integer, default=0)
    safety_score = Column(Float, default=100.0)

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


# ─── Social: User Follows ────────────────────────────────────────────────

class UserFollow(Base):
    __tablename__ = "user_follows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    follower_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    following_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Social: Shared Trips ────────────────────────────────────────────────

class SharedTrip(Base):
    __tablename__ = "shared_trips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    trip_id = Column(String(36), ForeignKey("trips.id"), nullable=False)
    caption = Column(Text, nullable=True)
    safety_score = Column(Integer, default=0)
    distance_km = Column(Float, default=0.0)
    duration_seconds = Column(Integer, default=0)
    route_polyline = Column(JSON, nullable=True)       # Sampled [{lat, lon}, ...]
    like_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Social: Trip Reactions ──────────────────────────────────────────────

class TripReaction(Base):
    __tablename__ = "trip_reactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    shared_trip_id = Column(Integer, ForeignKey("shared_trips.id"), nullable=False)
    reaction_type = Column(String(20), nullable=False)  # like, good_drive, warning
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Social: Community Posts ─────────────────────────────────────────────

class CommunityPost(Base):
    __tablename__ = "community_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    post_type = Column(String(30), default="general")   # hazard_report, route_recommendation, challenge_complete, general
    content = Column(Text, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    extra_data = Column(JSON, nullable=True)
    like_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Social: Driving Challenges ──────────────────────────────────────────

class DrivingChallenge(Base):
    __tablename__ = "driving_challenges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(50), default="🛡️")
    challenge_type = Column(String(30), nullable=False)  # streak, score, distance, trips
    target_value = Column(Integer, default=1)
    xp_reward = Column(Integer, default=10)
    period = Column(String(20), default="alltime")       # weekly, monthly, alltime
    is_active = Column(Boolean, default=True)


# ─── Social: User Challenge Progress ─────────────────────────────────────

class UserChallengeProgress(Base):
    __tablename__ = "user_challenge_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    challenge_id = Column(Integer, ForeignKey("driving_challenges.id"), nullable=False)
    current_value = Column(Integer, default=0)
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Social: Shared Routes ──────────────────────────────────────────────

class SharedRoute(Base):
    __tablename__ = "shared_routes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_lat = Column(Float, nullable=False)
    start_lon = Column(Float, nullable=False)
    end_lat = Column(Float, nullable=False)
    end_lon = Column(Float, nullable=False)
    route_polyline = Column(JSON, nullable=True)
    safety_score = Column(Integer, default=0)
    distance_km = Column(Float, default=0.0)
    follower_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Social: Notifications ───────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    type = Column(String(50), nullable=False)  # follow, reaction, challenge, system
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    extra_data = Column(JSON, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Emergency Profile (WheelSafar-Inspired: Digital QR Card) ────────────

class EmergencyProfile(Base):
    __tablename__ = "emergency_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, unique=True)
    full_name = Column(String(255), nullable=False)
    blood_type = Column(String(5), nullable=True)           # A+, A-, B+, B-, AB+, AB-, O+, O-
    allergies = Column(Text, nullable=True)                   # Comma-separated
    medical_conditions = Column(Text, nullable=True)          # Comma-separated
    medications = Column(Text, nullable=True)
    emergency_contact_1_name = Column(String(255), nullable=True)
    emergency_contact_1_phone = Column(String(20), nullable=True)
    emergency_contact_2_name = Column(String(255), nullable=True)
    emergency_contact_2_phone = Column(String(20), nullable=True)
    insurance_provider = Column(String(255), nullable=True)
    insurance_policy_no = Column(String(100), nullable=True)
    is_public = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Live Trip Session (WheelSafar-Inspired: Real-Time Location Sharing) ─

class LiveTripSession(Base):
    __tablename__ = "live_trip_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    trip_id = Column(String(36), ForeignKey("trips.id"), nullable=False)
    share_code = Column(String(8), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    latitude = Column(Float, default=0.0)
    longitude = Column(Float, default=0.0)
    speed_kph = Column(Float, default=0.0)
    risk_level = Column(String(10), default="LOW")
    alert_level = Column(String(10), default="GREEN")
    watcher_count = Column(Integer, default=0)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Quick Hazard Alerts (WheelSafar-Inspired: One-Tap Safety Alerts) ────

class QuickHazardAlert(Base):
    __tablename__ = "quick_hazard_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    alert_type = Column(String(30), nullable=False)    # breakdown, tricky_road, accident_ahead, road_hazard, police_checkpoint
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    speed_at_report = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    upvote_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True)


# ─── Ride Groups (WheelSafar-Inspired: Convoy & Group Tracking) ──────────

class RideGroup(Base):
    __tablename__ = "ride_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    invite_code = Column(String(6), unique=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("ride_groups.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    role = Column(String(20), default="MEMBER")  # ADMIN, MEMBER
    status = Column(String(20), default="JOINED") # JOINED, INVITED
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# ─── Digital Wallet ──────────────────────────────────────────────────────

class DigitalWallet(Base):
    __tablename__ = "wallets"

    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    
    # License Data
    license_no = Column(String(50), nullable=True)
    vehicle_classes = Column(String(50), nullable=True)
    license_dob = Column(String(20), nullable=True)
    blood_grp = Column(String(5), nullable=True)
    issue_date = Column(String(20), nullable=True)
    expiry_date = Column(String(20), nullable=True)
    license_pdf_url = Column(Text, nullable=True)

    # NIC Data
    nic_name = Column(String(255), nullable=True)
    nic_no = Column(String(20), nullable=True)
    nic_gender = Column(String(10), nullable=True)
    nic_pob = Column(String(100), nullable=True)
    nic_pdf_url = Column(Text, nullable=True)

    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship
    user = relationship("User", backref="wallet")
