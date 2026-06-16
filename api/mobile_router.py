"""
Mobile API Router — Endpoints for the Flutter App

This router handles all mobile-facing endpoints:
  POST /api/mobile/analyze          — Primary ingestion (called every 1-2s by the app)
  POST /api/mobile/users            — Register a new user
  GET  /api/mobile/users/{user_id}  — Get user profile
  POST /api/mobile/vehicles         — Add a vehicle to a user's garage
  GET  /api/mobile/vehicles/{uid}   — List user's vehicles
  GET  /api/mobile/trips/{vid}      — List trips for a vehicle
  POST /api/mobile/trips/{tid}/end  — End an active trip
  POST /api/mobile/blackspots       — Report a hazard (System 1)
  GET  /api/mobile/blackspots/nearby — Get nearby blackspots
  POST /api/mobile/claims           — File an insurance claim (System 2)
"""

import os
import math
import string
import random
import logging
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from fastapi.responses import HTMLResponse
import shutil
import uuid
from pathlib import Path
from sqlalchemy.orm import Session
import bcrypt
import hashlib

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    # Try bcrypt first
    try:
        if hashed_password.startswith('$2b$') or hashed_password.startswith('$2a$'):
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        pass
    
    # Fallback to SHA-256 (for passwords reset/changed from the admin panel)
    try:
        sha256_hash = hashlib.sha256(plain_password.encode('utf-8')).hexdigest()
        return sha256_hash == hashed_password
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

from .database import get_db
from .models import (
    User, Vehicle, Trip, TelemetryPoint,
    CrowdsourcedSign, BlackspotReport, InsuranceClaim, AccidentReport,
    PermanentHotspot, UserChallengeProgress, DrivingChallenge, Notification,
    EmergencyProfile, LiveTripSession, QuickHazardAlert, DigitalWallet,
    RideGroup, GroupMember, GroupAnnouncement, ConvoyPoll, ConvoyPollVote
)
from .schemas import (
    MobileAnalyzeRequest, MobileAnalyzeResponse,
    UserCreate, UserCreateWithPassword, UserResponse,
    EmailCheckRequest, EmailCheckResponse, LoginRequest,
    VehicleCreate, VehicleResponse,
    TripResponse, TripListResponse,
    TelemetryPointResponse, TripDetailResponse,
    BlackspotCreate, BlackspotResponse,
    InsuranceClaimCreate, InsuranceClaimResponse,
    HotspotItem, HotspotsListResponse,
    AccidentReportCreate, AccidentReportResponse,
    EmergencyProfileCreate, EmergencyProfileResponse,
    LiveTripStartRequest, LiveTripUpdateRequest, LiveTripResponse,
    QuickAlertCreate, QuickAlertResponse, QuickAlertsNearbyResponse,
    RideGroupCreate, RideGroupJoin, GroupMemberResponse, RideGroupResponse, GroupLiveLocationResponse,
    TelematicsEventRequest,
    EmergencySOSRequest, EmergencySOSResponse,
    WalletCreate, WalletResponse,
    ProfileUpdateRequest, VehicleUpdateRequest,
    ConvoyStartRequest, AnnouncementCreateRequest, GroupAnnouncementResponse, ConvoyLiveDetailsResponse, ConvoyMemberDetails,
    ConvoyPollCreateRequest, ConvoyPollVoteRequest, ConvoyPollResponse
)
from .circuit_breaker import CircuitBreaker

from src.fusion_engine import FusionEngine, TSRInput, DZInput, HotspotInput


logger = logging.getLogger("mobile_api")


def migrate_ride_groups_creator_id(db: Session):
    """
    Migrate existing ride groups to set creator_id.
    For groups without creator_id, assign the ADMIN member or first member as creator.
    """
    try:
        groups_without_creator = db.query(RideGroup).filter(RideGroup.creator_id == None).all()
        if not groups_without_creator:
            logger.info("All ride groups already have creator_id set")
            return

        for group in groups_without_creator:
            admin_member = db.query(GroupMember).filter(
                GroupMember.group_id == group.id,
                GroupMember.role == "ADMIN"
            ).first()

            if admin_member:
                group.creator_id = admin_member.user_id
            else:
                any_member = db.query(GroupMember).filter(
                    GroupMember.group_id == group.id
                ).first()
                if any_member:
                    group.creator_id = any_member.user_id

        db.commit()
        logger.info(f"Migrated {len(groups_without_creator)} ride groups with creator_id")
    except Exception as e:
        logger.error(f"Error migrating ride groups creator_id: {e}")
        db.rollback()


router = APIRouter(prefix="/api/mobile", tags=["Mobile App"])

# Reference to the shared fusion engine (set by main.py on startup)
_engine: FusionEngine = None
_config: dict = {}

# Circuit breakers (independent from the existing fusion API ones)
_cb_dz = CircuitBreaker("mobile_dz", failure_threshold=3, recovery_timeout=30)
_cb_tsr = CircuitBreaker("mobile_tsr", failure_threshold=3, recovery_timeout=30)


def init_mobile_router(engine: FusionEngine, config: dict):
    """Called by main.py after the fusion engine is initialized."""
    global _engine, _config
    _engine = engine
    _config = config


def _update_challenge_progress(user_id, ch_type, delta, db):
    """Internal helper to update user challenge progress."""
    progresses = db.query(UserChallengeProgress).filter(
        UserChallengeProgress.user_id == user_id,
        UserChallengeProgress.completed == False
    ).all()
    
    for p in progresses:
        ch = db.query(DrivingChallenge).filter(DrivingChallenge.id == p.challenge_id).first()
        if not ch or ch.challenge_type != ch_type:
            continue
            
        p.current_value += delta
        if p.current_value >= ch.target_value:
            p.completed = True
            p.completed_at = datetime.now(timezone.utc)
            # Reward XP
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.xp_points = (user.xp_points or 0) + ch.xp_reward
                # Notify
                notif = Notification(
                    user_id=user_id, type="challenge",
                    title="Challenge Completed!",
                    message=f"You completed '{ch.title}' and earned {ch.xp_reward} XP!",
                    extra_data={"challenge_id": ch.id}
                )
                db.add(notif)
    db.commit()


# ─── Primary Analyze Endpoint ────────────────────────────────────────────

@router.post("/analyze", response_model=MobileAnalyzeResponse)
async def mobile_analyze(request: MobileAnalyzeRequest, db: Session = Depends(get_db)):
    """
    Primary data ingestion endpoint for the Flutter app.
    
    Called every 1-2 seconds while the app is running.
    1. Creates or continues a Trip for this vehicle.
    2. Runs the Fusion Engine (DZ + optional TSR).
    3. Stores the telemetry point.
    4. Returns the risk score and LED alert level.
    """
    if _engine is None:
        raise HTTPException(status_code=503, detail="Fusion engine not initialized")

    # ─── Get or auto-create user ────────────────────────────────
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        # Auto-create user for demo mode or first-time mobile connections
        user = User(id=request.user_id, name="DriveGuard User", email=f"{request.user_id}@driveguard.app")
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Auto-created user: {user.id}")

    # ─── Get or auto-create vehicle ──────────────────────────────
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == request.vehicle_id
    ).first()
    if not vehicle:
        vehicle = Vehicle(
            id=request.vehicle_id,
            user_id=user.id,
            make_model="Demo Vehicle",
            vehicle_type="Car"
        )
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)
        logger.info(f"Auto-created vehicle: {vehicle.id} for user {user.id}")

    # ─── Get or create active trip ───────────────────────────────
    trip = None
    if request.trip_id:
        trip = db.query(Trip).filter(
            Trip.id == request.trip_id,
            Trip.is_active == True
        ).first()

    if not trip:
        # Auto-create a new trip
        trip = Trip(vehicle_id=vehicle.id)
        db.add(trip)
        db.commit()
        db.refresh(trip)
        _engine.reset()  # Reset fusion engine state for new trip
        logger.info(f"New trip started: {trip.id} for vehicle {vehicle.make_model}")

    # ─── Initialize Ingestion Parameters & Status ───────────────
    tsr_url = _config.get("tsr_url", "http://localhost:8001")
    tsr_endpoint = _config.get("tsr_endpoint", "/api/predict/base64")
    dz_url = _config.get("dz_url", "http://localhost:8000")
    dz_endpoint = _config.get("dz_endpoint", "/api/predict")
    degraded = False

    tsr = None
    recent_hazard = "None"
    dz = None

    # ─── Asynchronous Client Context for External Module Calls ───
    headers = {"x-api-key": os.getenv("DG_API_KEY", "")}
    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        # 1. Call TSR Module (Perception) if image provided
        if request.image_base64 and _cb_tsr.can_execute():
            try:
                tsr_resp = await client.post(
                    f"{tsr_url}{tsr_endpoint}",
                    json={"image": request.image_base64, "is_cropped": request.is_cropped}
                )
                tsr_data = tsr_resp.json()
                tsr = TSRInput(
                    class_id=tsr_data.get("class_id", 0),
                    class_name=tsr_data.get("class_name", "unknown"),
                    confidence=tsr_data.get("confidence", 0),
                    is_confident=tsr_data.get("is_confident", False),
                    latitude=request.latitude,
                    longitude=request.longitude,
                    bbox=tsr_data.get("bbox")
                )
                _cb_tsr.record_success()
                
                # Extract hazard for DZ model if confidence is high
                if tsr.is_confident and tsr.confidence > 0.8:
                    recent_hazard = tsr.class_name
                    
                if tsr.confidence >= 0.85:
                    # Estimate sign location 25m ahead of vehicle heading
                    import math
                    dist_km = 0.025 # 25 meters
                    R = 6371.0 # Earth radius
                    brng = math.radians(request.heading)
                    lat1 = math.radians(request.latitude)
                    lon1 = math.radians(request.longitude)
                    
                    lat2 = math.asin(math.sin(lat1)*math.cos(dist_km/R) + 
                                     math.cos(lat1)*math.sin(dist_km/R)*math.cos(brng))
                    lon2 = lon1 + math.atan2(math.sin(brng)*math.sin(dist_km/R)*math.cos(lat1),
                                             math.cos(dist_km/R)-math.sin(lat1)*math.sin(lat2))
                    
                    est_lat, est_lon = math.degrees(lat2), math.degrees(lon2)
                    # The user requested that signs are ONLY updated by admins.
                    # Mobile app will visualize it (returned in response) but won't save it to the DB.
                    # _save_crowdsourced_sign(db, tsr, est_lat, est_lon)
            except Exception as e:
                _cb_tsr.record_failure()
                logger.warning(f"TSR module call failed: {e}")
                degraded = True

        # 2. Call DZ Module (Reasoning)
        if _cb_dz.can_execute():
            try:
                dz_resp = await client.post(
                    f"{dz_url}{dz_endpoint}",
                    json={
                        "latitude": request.latitude,
                        "longitude": request.longitude,
                        "heading": request.heading,
                        "speed_kph": request.speed_kph,
                        "scenario": "realtime",
                        "live_hazard": recent_hazard
                    }
                )
                dz_data = dz_resp.json()
                dz = DZInput(
                    risk_score=dz_data.get("risk_score", 0),
                    risk_level=dz_data.get("risk_level", "LOW"),
                    confidence=dz_data.get("confidence", 0.5),
                    risk_probability=dz_data.get("risk_score", 0) / 100.0,
                    weather_condition=dz_data.get("weather_condition", "Fine"),
                    road_surface=dz_data.get("road_surface", "Dry"),
                    is_overspeeding=dz_data.get("is_overspeeding", False),
                    speed_deviation_kph=dz_data.get("speed_deviation_kph", 0),
                    speed_kph=request.speed_kph,
                    reasons=dz_data.get("reasons", [])
                )
                _cb_dz.record_success()
            except Exception as e:
                _cb_dz.record_failure()
                logger.error(f"DZ module call failed: {e}")

    # ─── DZ Fallback ────────────────────────────────────────────
    if dz is None:
        degraded = True
        speed = request.speed_kph
        fallback_risk = min(speed * 0.8, 70)
        fallback_level = "HIGH" if fallback_risk > 60 else "MEDIUM" if fallback_risk > 30 else "LOW"
        dz = DZInput(
            risk_score=fallback_risk, risk_level=fallback_level,
            confidence=0.3, risk_probability=fallback_risk / 100.0,
            weather_condition="Fine", road_surface="Dry",
            speed_kph=speed,
            reasons=[{"feature": "fallback", "direction": "info",
                      "description": "DZ module unavailable — speed-based estimate"}]
        )

    # ─── TSR Virtualization (Always run if no active visual sign) ───
    if tsr is None:
        virtual_tsr = _lookup_virtual_sign(db, request.latitude, request.longitude)
        if virtual_tsr:
            tsr = virtual_tsr
            logger.debug(f"Virtual TSR: {tsr.class_name} from cloud sign map")

    # ── Check nearby blackspots (System 1) ───────────────────
    hotspot = _check_nearby_blackspots(db, request.latitude, request.longitude)

    # ── Run Fusion ───────────────────────────────────────────
    result = _engine.fuse(dz_input=dz, tsr_input=tsr, hotspot_input=hotspot)

    # ── Determine LED alert level ────────────────────────────
    alert_level = "GREEN"
    if result.fused_risk_score >= 65:
        alert_level = "RED"
    elif result.fused_risk_score >= 35:
        alert_level = "YELLOW"

    # ── Calculate Distance & Store telemetry point ───────────
    last_point = db.query(TelemetryPoint).filter(
        TelemetryPoint.trip_id == trip.id
    ).order_by(TelemetryPoint.timestamp.desc()).first()
    
    if last_point:
        dist_km = _haversine(last_point.latitude, last_point.longitude, request.latitude, request.longitude)
        trip.total_distance_km = (trip.total_distance_km or 0.0) + dist_km

    detected_sign_names = [s.get("class_name", "") for s in result.active_signs] if result.active_signs else []

    point = TelemetryPoint(
        trip_id=trip.id,
        latitude=request.latitude,
        longitude=request.longitude,
        speed_kph=request.speed_kph,
        heading=request.heading,
        risk_score=result.fused_risk_score,
        risk_level=result.fused_risk_level,
        alert_level=alert_level,
        detected_signs=detected_sign_names,
        belief_dangerous=result.belief_dangerous,
        conflict_measure=result.conflict_measure
    )
    db.add(point)

    # ── Update trip aggregates ───────────────────────────────
    trip.point_count += 1
    trip.max_risk_score = max(trip.max_risk_score, result.fused_risk_score)
    # Running average
    trip.avg_risk_score = (
        (trip.avg_risk_score * (trip.point_count - 1) + result.fused_risk_score)
        / trip.point_count
    )
    if alert_level == "RED":
        trip.red_alert_count += 1
    elif alert_level == "YELLOW":
        trip.yellow_alert_count += 1

    # ─── Finalize ────────────────────────────────────────────────
    db.commit()
    
    # Update distance progress if any distance challenge is active
    _update_challenge_progress(user.id, "distance", dz.speed_kph / 3600.0, db) # roughly km/s if called every 1s

    # ── Build simplified response ────────────────────────────
    reason_strings = [
        r.get("description", "") for r in result.fusion_reasons
    ] if result.fusion_reasons else []

    return MobileAnalyzeResponse(
        trip_id=trip.id,
        risk_score=round(result.fused_risk_score, 1),
        risk_level=result.fused_risk_level,
        alert_level=alert_level,
        detected_signs=detected_sign_names,
        belief_dangerous=round(result.belief_dangerous, 3),
        fused_confidence=round(result.fused_confidence, 3),
        is_degraded=degraded,
        fusion_reasons=reason_strings
    )


# ─── User CRUD ────────────────────────────────────────────────────────────

@router.post("/auth/check-email", response_model=EmailCheckResponse)
async def check_email(data: EmailCheckRequest, db: Session = Depends(get_db)):
    """Check if an email is already registered."""
    email_clean = data.email.strip().lower()
    existing = db.query(User).filter(User.email.ilike(email_clean)).first()
    return EmailCheckResponse(exists=bool(existing))


@router.post("/auth/login", response_model=UserResponse)
async def login(data: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate a user."""
    email_clean = data.email.strip().lower()
    user = db.query(User).filter(User.email.ilike(email_clean)).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    return UserResponse(
        id=user.id, name=user.name, email=user.email,
        profile_picture_url=user.profile_picture_url,
        created_at=str(user.created_at), vehicle_count=len(user.vehicles)
    )

@router.post("/users", response_model=UserResponse)
async def create_user(data: UserCreateWithPassword, db: Session = Depends(get_db)):
    """Register a new DriveGuard user with password."""
    email_clean = data.email.strip().lower()
    existing = db.query(User).filter(User.email.ilike(email_clean)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        name=data.name, 
        email=email_clean, 
        password_hash=get_password_hash(data.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse(
        id=user.id, name=user.name, email=user.email,
        profile_picture_url=user.profile_picture_url,
        created_at=str(user.created_at), vehicle_count=0
    )


@router.post("/users/{user_id}/profile-picture", response_model=UserResponse)
async def upload_profile_picture(
    user_id: str, 
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    """Upload a profile picture for a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    uploads_dir = Path(__file__).parent.parent / "uploads" / "profiles"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    
    ext = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
    filename = f"{user_id}_{uuid.uuid4().hex[:8]}.{ext}"
    file_path = uploads_dir / filename
    
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    user.profile_picture_url = f"/uploads/profiles/{filename}"
    db.commit()
    db.refresh(user)
    
    return UserResponse(
        id=user.id, name=user.name, email=user.email,
        profile_picture_url=user.profile_picture_url,
        created_at=str(user.created_at), vehicle_count=len(user.vehicles)
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, db: Session = Depends(get_db)):
    """Get user profile."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(
        id=user.id, name=user.name, email=user.email,
        profile_picture_url=user.profile_picture_url,
        created_at=str(user.created_at),
        vehicle_count=len(user.vehicles)
    )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, data: ProfileUpdateRequest, db: Session = Depends(get_db)):
    """Update user profile from the mobile app."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.name is not None:
        user.name = data.name
    # if data.bio is not None:
    #     user.bio = data.bio
    # if data.avatar_color is not None:
    #     user.avatar_color = data.avatar_color

    db.commit()
    db.refresh(user)

    return UserResponse(
        id=user.id, name=user.name, email=user.email,
        profile_picture_url=user.profile_picture_url,
        created_at=str(user.created_at),
        vehicle_count=len(user.vehicles)
    )


# ─── Vehicle CRUD (The Garage) ────────────────────────────────────────────

@router.post("/users/{user_id}/vehicles", response_model=VehicleResponse)
async def add_vehicle(user_id: str, data: VehicleCreate, db: Session = Depends(get_db)):
    """Add a vehicle to a user's garage."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    vehicle = Vehicle(
        user_id=user_id,
        make_model=data.make_model,
        vehicle_type=data.vehicle_type,
        registration_number=data.registration_number,
        led_stick_mac=data.led_stick_mac
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return VehicleResponse(
        id=vehicle.id, user_id=vehicle.user_id,
        make_model=vehicle.make_model, vehicle_type=vehicle.vehicle_type,
        registration_number=vehicle.registration_number,
        led_stick_mac=vehicle.led_stick_mac,
        created_at=str(vehicle.created_at), trip_count=0
    )


@router.get("/users/{user_id}/vehicles", response_model=list[VehicleResponse])
async def list_vehicles(user_id: str, db: Session = Depends(get_db)):
    """List all vehicles in a user's garage."""
    vehicles = db.query(Vehicle).filter(Vehicle.user_id == user_id).all()
    return [
        VehicleResponse(
            id=v.id, user_id=v.user_id,
            make_model=v.make_model, vehicle_type=v.vehicle_type,
            registration_number=v.registration_number,
            led_stick_mac=v.led_stick_mac,
            created_at=str(v.created_at),
            trip_count=len(v.trips)
        )
        for v in vehicles
    ]


@router.put("/vehicles/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(vehicle_id: str, data: VehicleUpdateRequest, db: Session = Depends(get_db)):
    """Update vehicle details from the mobile app."""
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    if data.make_model is not None:
        vehicle.make_model = data.make_model
    if data.vehicle_type is not None:
        vehicle.vehicle_type = data.vehicle_type
    if data.registration_number is not None:
        vehicle.registration_number = data.registration_number
    if data.led_stick_mac is not None:
        vehicle.led_stick_mac = data.led_stick_mac

    db.commit()
    db.refresh(vehicle)

    return VehicleResponse(
        id=vehicle.id, user_id=vehicle.user_id,
        make_model=vehicle.make_model, vehicle_type=vehicle.vehicle_type,
        registration_number=vehicle.registration_number,
        led_stick_mac=vehicle.led_stick_mac,
        created_at=str(vehicle.created_at), trip_count=len(vehicle.trips)
    )


@router.delete("/vehicles/{vehicle_id}")
async def delete_vehicle(vehicle_id: str, db: Session = Depends(get_db)):
    """Delete a vehicle."""
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    db.delete(vehicle)
    db.commit()
    return {"detail": "Vehicle deleted successfully"}


# ─── Trip Endpoints ──────────────────────────────────────────────────────

@router.get("/vehicles/{vehicle_id}/trips", response_model=TripListResponse)
async def list_trips(vehicle_id: str, db: Session = Depends(get_db)):
    """List all trips for a vehicle (newest first)."""
    trips = db.query(Trip).filter(
        Trip.vehicle_id == vehicle_id
    ).order_by(Trip.start_time.desc()).limit(50).all()
    return TripListResponse(
        count=len(trips),
        trips=[
            TripResponse(
                id=t.id, vehicle_id=t.vehicle_id,
                start_time=str(t.start_time),
                end_time=str(t.end_time) if t.end_time else None,
                is_active=t.is_active,
                avg_risk_score=round(t.avg_risk_score, 1),
                max_risk_score=round(t.max_risk_score, 1),
                total_distance_km=round(t.total_distance_km, 2),
                red_alert_count=t.red_alert_count,
                yellow_alert_count=t.yellow_alert_count,
                point_count=t.point_count,
                hard_brake_count=t.hard_brake_count,
                harsh_corner_count=t.harsh_corner_count,
                safety_score=round(t.safety_score, 1)
            )
            for t in trips
        ]
    )


def _compute_safety_score(trip):
    penalties = 0
    penalties += (trip.hard_brake_count or 0) * 10
    penalties += (trip.harsh_corner_count or 0) * 8
    penalties += (trip.red_alert_count or 0) * 5
    penalties += (trip.yellow_alert_count or 0) * 2
    
    distance = trip.total_distance_km or 0.0
    distance_factor = max(1.0, distance / 10.0)
    
    normalized_penalty = penalties / distance_factor
    score = 100 - normalized_penalty
    
    # Bonuses for safe driving
    if (trip.red_alert_count or 0) == 0 and (trip.hard_brake_count or 0) == 0:
        score += 5
    if (trip.point_count or 0) > 50 and (trip.avg_risk_score or 0) < 20: 
        score += 3
        
    return max(0.0, min(100.0, score))

@router.post("/trips/{trip_id}/end")
async def end_trip(trip_id: str, db: Session = Depends(get_db)):
    """End an active trip."""
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.is_active == True).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Active trip not found")
    trip.is_active = False
    trip.end_time = datetime.now(timezone.utc)
    
    # ─── Challenge Updates ──────────────────────────────
    vehicle = db.query(Vehicle).filter(Vehicle.id == trip.vehicle_id).first()
    if vehicle:
        score = _compute_safety_score(trip)
        trip.safety_score = score
        _update_challenge_progress(vehicle.user_id, "score", score, db)
        _update_challenge_progress(vehicle.user_id, "trips", 1, db)
        
        # Update user aggregated stats
        user = db.query(User).filter(User.id == vehicle.user_id).first()
        if user:
            user.total_trips = (user.total_trips or 0) + 1
            user.total_distance_km = (user.total_distance_km or 0.0) + (trip.total_distance_km or 0.0)
            # Recalculate average safety score
            user.safety_score = ((user.safety_score or 100.0) * (user.total_trips - 1) + score) / user.total_trips
    
    db.commit()
    return {"status": "ended", "trip_id": trip.id, "avg_risk": round(trip.avg_risk_score, 1), "safety_score": score if vehicle else 0}


@router.get("/trips/{trip_id}/points", response_model=TripDetailResponse)
async def get_trip_points(trip_id: str, db: Session = Depends(get_db)):
    """
    Get all telemetry points for a trip (for Trip Replay).
    Returns the full GPS trail with risk data at each point.
    """
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    points = db.query(TelemetryPoint).filter(
        TelemetryPoint.trip_id == trip_id
    ).order_by(TelemetryPoint.timestamp.asc()).all()

    return TripDetailResponse(
        trip=TripResponse(
            id=trip.id, vehicle_id=trip.vehicle_id,
            start_time=str(trip.start_time),
            end_time=str(trip.end_time) if trip.end_time else None,
            is_active=trip.is_active,
            avg_risk_score=round(trip.avg_risk_score, 1),
            max_risk_score=round(trip.max_risk_score, 1),
            total_distance_km=round(trip.total_distance_km, 2),
            red_alert_count=trip.red_alert_count,
            yellow_alert_count=trip.yellow_alert_count,
            point_count=trip.point_count,
            hard_brake_count=trip.hard_brake_count,
            harsh_corner_count=trip.harsh_corner_count,
            safety_score=round(trip.safety_score, 1)
        ),
        points=[
            TelemetryPointResponse(
                latitude=p.latitude,
                longitude=p.longitude,
                speed_kph=p.speed_kph,
                heading=p.heading,
                risk_score=p.risk_score,
                risk_level=p.risk_level,
                alert_level=p.alert_level,
                detected_signs=p.detected_signs or [],
                timestamp=str(p.timestamp)
            )
            for p in points
        ],
        total_points=len(points)
    )


# ─── Blackspot Reports (System 1: Crowdsourced Hazard Markers) ───────────

@router.post("/blackspots", response_model=BlackspotResponse)
async def report_blackspot(
    user_id: str,
    data: BlackspotCreate,
    db: Session = Depends(get_db)
):
    """Report a hazard/blackspot at a GPS location."""
    report = BlackspotReport(
        user_id=user_id,
        latitude=data.latitude,
        longitude=data.longitude,
        description=data.description,
        report_type=data.report_type,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # ── Automated Promotion Pipeline ──
    # Check if there are 3 or more reports within 50 meters
    now = datetime.now(timezone.utc)
    recent_reports = db.query(BlackspotReport).filter(
        BlackspotReport.expires_at > now
    ).all()

    cluster = []
    for r in recent_reports:
        if _haversine(data.latitude, data.longitude, r.latitude, r.longitude) <= 0.05: # 50 meters
            cluster.append(r)

    if len(cluster) >= 3:
        # Calculate center point
        avg_lat = sum(r.latitude for r in cluster) / len(cluster)
        avg_lon = sum(r.longitude for r in cluster) / len(cluster)
        
        # Create Permanent Hotspot
        hotspot = PermanentHotspot(
            latitude=avg_lat,
            longitude=avg_lon,
            name=f"Auto-Promoted Hotspot ({data.report_type})",
            report_count=len(cluster),
            risk_boost=min(0.2 * len(cluster), 0.8),
            is_active=True
        )
        db.add(hotspot)
        
        # Delete the temporary reports since they are now permanent
        for r in cluster:
            db.delete(r)
            
        db.commit()

    # Note: If it was promoted, the response still returns the initial report data 
    # to the mobile app for confirmation, but it's already a permanent hotspot in DB.
    return BlackspotResponse(
        id=report.id, user_id=report.user_id,
        latitude=report.latitude, longitude=report.longitude,
        description=report.description, report_type=report.report_type,
        created_at=str(report.created_at)
    )


@router.get("/blackspots/nearby")
async def get_nearby_blackspots(
    lat: float, lon: float, radius_km: float = 2.0,
    db: Session = Depends(get_db)
):
    """Get active blackspot reports within a radius of a GPS point."""
    now = datetime.now(timezone.utc)
    reports = db.query(BlackspotReport).filter(
        BlackspotReport.expires_at > now
    ).all()

    nearby = []
    for r in reports:
        dist = _haversine(lat, lon, r.latitude, r.longitude)
        if dist <= radius_km:
            nearby.append({
                "id": r.id,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "description": r.description,
                "report_type": r.report_type,
                "hazard_type": r.report_type,  # alias for mobile compatibility
                "distance_km": round(dist, 2)
            })
    return {"count": len(nearby), "blackspots": nearby}


# ─── Insurance Claims (System 2: Official Accident Reporting) ────────────

@router.post("/users/{user_id}/claims", response_model=InsuranceClaimResponse)
async def file_claim(
    user_id: str,
    data: InsuranceClaimCreate,
    db: Session = Depends(get_db)
):
    """File an insurance claim with pre-crash telemetry."""
    # Look up the most recent telemetry for pre-crash data (most accurate source)
    pre_crash_speed = None
    pre_crash_risk = None
    weather = None

    if data.trip_id:
        latest_point = db.query(TelemetryPoint).filter(
            TelemetryPoint.trip_id == data.trip_id
        ).order_by(TelemetryPoint.timestamp.desc()).first()

        if latest_point:
            pre_crash_speed = latest_point.speed_kph
            pre_crash_risk = latest_point.risk_score

    # Fallback to client-provided snapshot if telemetry not available
    # (e.g. drive not started, or brief connectivity loss at moment of impact)
    if pre_crash_speed is None:
        pre_crash_speed = data.pre_crash_speed_kph
    if pre_crash_risk is None:
        pre_crash_risk = data.pre_crash_risk_score

    claim = InsuranceClaim(
        user_id=user_id,
        vehicle_id=data.vehicle_id,
        trip_id=data.trip_id,
        latitude=data.latitude,
        longitude=data.longitude,
        pre_crash_speed_kph=pre_crash_speed,
        pre_crash_risk_score=pre_crash_risk,
        weather_condition=weather,
        statement=data.statement,
        photo_urls=data.photo_urls,
        status="DRAFT"
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)

    return InsuranceClaimResponse(
        id=claim.id, user_id=claim.user_id,
        vehicle_id=claim.vehicle_id, trip_id=claim.trip_id,
        latitude=claim.latitude, longitude=claim.longitude,
        pre_crash_speed_kph=claim.pre_crash_speed_kph,
        pre_crash_risk_score=claim.pre_crash_risk_score,
        weather_condition=claim.weather_condition,
        statement=claim.statement, photo_urls=claim.photo_urls,
        status=claim.status, created_at=str(claim.created_at)
    )


# ─── Helper Functions ────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two GPS points in km."""
    R = 6371  # Earth radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _save_crowdsourced_sign(db: Session, tsr: TSRInput, lat: float, lon: float):
    """Save a high-confidence sign detection to the cloud sign map."""
    existing = db.query(CrowdsourcedSign).filter(
        CrowdsourcedSign.class_id == tsr.class_id,
        CrowdsourcedSign.latitude.between(lat - 0.0005, lat + 0.0005),
        CrowdsourcedSign.longitude.between(lon - 0.0005, lon + 0.0005)
    ).first()

    if existing:
        existing.report_count += 1
        existing.last_seen = datetime.now(timezone.utc)
        existing.confidence = max(existing.confidence, tsr.confidence)
    else:
        sign = CrowdsourcedSign(
            latitude=lat, longitude=lon,
            class_id=tsr.class_id, class_name=tsr.class_name,
            confidence=tsr.confidence
        )
        db.add(sign)

    db.commit()


def _lookup_virtual_sign(db: Session, lat: float, lon: float) -> TSRInput:
    """Look up crowdsourced signs near this GPS location (TSR Virtualization)."""
    signs = db.query(CrowdsourcedSign).filter(
        CrowdsourcedSign.latitude.between(lat - 0.001, lat + 0.001),
        CrowdsourcedSign.longitude.between(lon - 0.001, lon + 0.001),
        CrowdsourcedSign.report_count >= 2  # Only use signs confirmed by 2+ users
    ).order_by(CrowdsourcedSign.confidence.desc()).first()

    if signs:
        return TSRInput(
            class_id=signs.class_id,
            class_name=signs.class_name,
            confidence=min(signs.confidence * 0.9, 0.95),  # Slightly reduce confidence for virtual
            is_confident=True,
            latitude=lat,
            longitude=lon
        )
    return None


def _check_nearby_blackspots(db: Session, lat: float, lon: float) -> HotspotInput:
    """Check if there are active blackspot reports near this location."""
    now = datetime.now(timezone.utc)
    reports = db.query(BlackspotReport).filter(
        BlackspotReport.expires_at > now,
        BlackspotReport.latitude.between(lat - 0.005, lat + 0.005),
        BlackspotReport.longitude.between(lon - 0.005, lon + 0.005)
    ).all()

    if reports:
        nearby = [r for r in reports if _haversine(lat, lon, r.latitude, r.longitude) < 0.5]
        if nearby:
            return HotspotInput(
                risk_boost=min(0.3 * len(nearby), 0.8),
                report_count=len(nearby)
            )
    return None


# ─── Permanent Hotspots (Direct DB Read) ─────────────────────────────────

@router.get("/hotspots", response_model=HotspotsListResponse)
async def get_hotspots(db: Session = Depends(get_db)):
    """Get permanent accident hotspots directly from the database."""
    try:
        rows = db.query(PermanentHotspot).all()
        hotspots = [
            HotspotItem(
                id=h.id,
                name=h.name or "Unknown",
                latitude=h.latitude,
                longitude=h.longitude,
                report_count=h.report_count or 0,
                risk_boost=h.risk_boost or 0.0,
                created_at=str(h.first_reported) if h.first_reported else None,
            )
            for h in rows
        ]
        if not hotspots:
            # Fallback to hardcoded demo hotspots if DB is empty or unreachable
            hotspots = [
                HotspotItem(id=1, name="Borella Junction", latitude=6.9147, longitude=79.8775, risk_boost=0.8),
                HotspotItem(id=2, name="Lipton Circus", latitude=6.9073, longitude=79.8638, risk_boost=0.6),
                HotspotItem(id=3, name="Baseline Road", latitude=6.9191, longitude=79.8819, risk_boost=0.7),
            ]
        return HotspotsListResponse(count=len(hotspots), hotspots=hotspots)
    except Exception as e:
        logger.error(f"Failed to fetch hotspots: {e}")
        return HotspotsListResponse(count=0, hotspots=[])


# ─── Accident Reports (Police Reporting) ─────────────────────────────────

@router.post("/accident-report", response_model=AccidentReportResponse)
async def submit_accident_report(
    user_id: str,
    data: AccidentReportCreate,
    db: Session = Depends(get_db),
):
    """Submit a police/accident report at the current GPS location."""
    report = AccidentReport(
        user_id=user_id,
        latitude=data.latitude,
        longitude=data.longitude,
        severity=data.severity,
        description=data.description,
        vehicles_involved=data.vehicles_involved,
        injuries=data.injuries,
        police_notified=data.police_notified,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return AccidentReportResponse(
        id=report.id,
        user_id=report.user_id,
        latitude=report.latitude,
        longitude=report.longitude,
        severity=report.severity,
        description=report.description,
        vehicles_involved=report.vehicles_involved,
        injuries=report.injuries,
        police_notified=report.police_notified,
        status=report.status,
        created_at=str(report.created_at),
    )


# ═══════════════════════════════════════════════════════════════════════════
# WheelSafar-Inspired Features
# ═══════════════════════════════════════════════════════════════════════════


# ─── Emergency Profile (Digital QR Card) ─────────────────────────────────

@router.get("/emergency-profile/{user_id}", response_model=EmergencyProfileResponse)
async def get_emergency_profile(user_id: str, db: Session = Depends(get_db)):
    """Get a user's emergency profile."""
    profile = db.query(EmergencyProfile).filter(EmergencyProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Emergency profile not found")
    return EmergencyProfileResponse(
        id=profile.id, user_id=profile.user_id,
        full_name=profile.full_name, blood_type=profile.blood_type,
        allergies=profile.allergies, medical_conditions=profile.medical_conditions,
        medications=profile.medications,
        emergency_contact_1_name=profile.emergency_contact_1_name,
        emergency_contact_1_phone=profile.emergency_contact_1_phone,
        emergency_contact_2_name=profile.emergency_contact_2_name,
        emergency_contact_2_phone=profile.emergency_contact_2_phone,
        insurance_provider=profile.insurance_provider,
        insurance_policy_no=profile.insurance_policy_no,
        is_public=profile.is_public,
        created_at=str(profile.created_at),
        updated_at=str(profile.updated_at),
    )


@router.put("/emergency-profile/{user_id}", response_model=EmergencyProfileResponse)
async def upsert_emergency_profile(
    user_id: str, data: EmergencyProfileCreate, db: Session = Depends(get_db)
):
    """Create or update a user's emergency profile."""
    profile = db.query(EmergencyProfile).filter(EmergencyProfile.user_id == user_id).first()
    if profile:
        for field, value in data.model_dump().items():
            setattr(profile, field, value)
        profile.updated_at = datetime.now(timezone.utc)
    else:
        profile = EmergencyProfile(user_id=user_id, **data.model_dump())
        db.add(profile)
    db.commit()
    db.refresh(profile)
    return EmergencyProfileResponse(
        id=profile.id, user_id=profile.user_id,
        full_name=profile.full_name, blood_type=profile.blood_type,
        allergies=profile.allergies, medical_conditions=profile.medical_conditions,
        medications=profile.medications,
        emergency_contact_1_name=profile.emergency_contact_1_name,
        emergency_contact_1_phone=profile.emergency_contact_1_phone,
        emergency_contact_2_name=profile.emergency_contact_2_name,
        emergency_contact_2_phone=profile.emergency_contact_2_phone,
        insurance_provider=profile.insurance_provider,
        insurance_policy_no=profile.insurance_policy_no,
        is_public=profile.is_public,
        created_at=str(profile.created_at),
        updated_at=str(profile.updated_at),
    )


@router.get("/emergency-card/{user_id}", response_class=HTMLResponse)
async def get_emergency_card(user_id: str, db: Session = Depends(get_db)):
    """
    Public HTML emergency card — scannable via QR code.
    No authentication required. Displays critical medical info.
    """
    profile = db.query(EmergencyProfile).filter(
        EmergencyProfile.user_id == user_id
    ).first()

    if not profile or not profile.is_public:
        return HTMLResponse(content="""
        <html><head><meta name="viewport" content="width=device-width,initial-scale=1">
        <style>body{font-family:system-ui;background:#0A0E21;color:#fff;display:flex;
        align-items:center;justify-content:center;min-height:100vh;margin:0;}
        .card{text-align:center;padding:40px;}
        h1{color:#00E676;}</style></head>
        <body><div class="card"><h1>🛡️ DriveGuard</h1>
        <p>Emergency profile not available.</p></div></body></html>
        """, status_code=200)

    # Build the emergency card HTML
    contacts_html = ""
    if profile.emergency_contact_1_name:
        phone1 = profile.emergency_contact_1_phone or ""
        contacts_html += f'<div class="contact"><span class="label">📞 Contact 1</span><strong>{profile.emergency_contact_1_name}</strong><a href="tel:{phone1}" class="phone">{phone1}</a></div>'
    if profile.emergency_contact_2_name:
        phone2 = profile.emergency_contact_2_phone or ""
        contacts_html += f'<div class="contact"><span class="label">📞 Contact 2</span><strong>{profile.emergency_contact_2_name}</strong><a href="tel:{phone2}" class="phone">{phone2}</a></div>'

    html = f"""
    <html><head>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Emergency Card — {profile.full_name}</title>
    <style>
      * {{ margin:0; padding:0; box-sizing:border-box; }}
      body {{ font-family:'Segoe UI',system-ui,sans-serif; background:#0A0E21; color:#E0E0E0;
             min-height:100vh; padding:20px; }}
      .card {{ max-width:420px; margin:0 auto; }}
      .header {{ text-align:center; padding:24px 0; border-bottom:1px solid rgba(255,255,255,0.08); }}
      .header h1 {{ color:#00E676; font-size:14px; letter-spacing:2px; text-transform:uppercase; margin-bottom:8px; }}
      .header .name {{ font-size:28px; font-weight:800; color:#fff; }}
      .badge {{ display:inline-block; background:#FF5252; color:#fff; padding:4px 14px;
               border-radius:20px; font-size:13px; font-weight:700; margin-top:10px; }}
      .section {{ padding:16px 0; border-bottom:1px solid rgba(255,255,255,0.06); }}
      .section-title {{ color:#00E676; font-size:11px; letter-spacing:1.5px; text-transform:uppercase;
                        margin-bottom:10px; font-weight:600; }}
      .field {{ display:flex; justify-content:space-between; padding:6px 0; }}
      .field .label {{ color:#888; font-size:13px; }}
      .field .value {{ color:#fff; font-weight:600; font-size:13px; }}
      .contact {{ background:rgba(255,255,255,0.04); border-radius:12px; padding:12px 16px;
                  margin-bottom:8px; }}
      .contact .label {{ color:#888; font-size:11px; display:block; }}
      .contact strong {{ color:#fff; font-size:15px; display:block; margin:4px 0; }}
      .contact .phone {{ color:#00E676; text-decoration:none; font-size:18px; font-weight:700; }}
      .footer {{ text-align:center; padding:20px 0; color:#444; font-size:11px; }}
    </style></head>
    <body><div class="card">
      <div class="header">
        <h1>🛡️ DriveGuard Emergency Card</h1>
        <div class="name">{profile.full_name}</div>
        {'<div class="badge">🩸 ' + profile.blood_type + '</div>' if profile.blood_type else ''}
      </div>
      <div class="section">
        <div class="section-title">Medical Information</div>
        {'<div class="field"><span class="label">Allergies</span><span class="value">' + (profile.allergies or 'None') + '</span></div>' }
        {'<div class="field"><span class="label">Conditions</span><span class="value">' + (profile.medical_conditions or 'None') + '</span></div>'}
        {'<div class="field"><span class="label">Medications</span><span class="value">' + (profile.medications or 'None') + '</span></div>'}
      </div>
      <div class="section">
        <div class="section-title">Emergency Contacts</div>
        {contacts_html if contacts_html else '<p style="color:#666">No contacts listed</p>'}
      </div>
      {'<div class="section"><div class="section-title">Insurance</div><div class="field"><span class="label">Provider</span><span class="value">' + (profile.insurance_provider or 'N/A') + '</span></div><div class="field"><span class="label">Policy No.</span><span class="value">' + (profile.insurance_policy_no or 'N/A') + '</span></div></div>' if profile.insurance_provider else ''}
      <div class="footer">Generated by DriveGuard — Scan QR for instant access</div>
    </div></body></html>
    """
    return HTMLResponse(content=html)


# ─── Live Trip Sharing ───────────────────────────────────────────────────

def _generate_share_code() -> str:
    """Generate a short, unique share code like DG-X7K2."""
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choices(chars, k=4))
    return f"DG-{code}"


@router.post("/live-trip/start", response_model=LiveTripResponse)
async def start_live_trip(data: LiveTripStartRequest, db: Session = Depends(get_db)):
    """Start broadcasting a live trip. Returns a share code."""
    # End any existing active sessions for this user
    db.query(LiveTripSession).filter(
        LiveTripSession.user_id == data.user_id,
        LiveTripSession.is_active == True
    ).update({"is_active": False})

    # Generate unique share code
    for _ in range(10):
        code = _generate_share_code()
        existing = db.query(LiveTripSession).filter(LiveTripSession.share_code == code).first()
        if not existing:
            break

    session = LiveTripSession(
        user_id=data.user_id,
        trip_id=data.trip_id,
        share_code=code,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    user = db.query(User).filter(User.id == data.user_id).first()
    return LiveTripResponse(
        id=session.id, user_id=session.user_id,
        user_name=user.name if user else "",
        trip_id=session.trip_id, share_code=session.share_code,
        is_active=True, watcher_count=0,
        last_updated=str(session.last_updated),
        created_at=str(session.created_at),
    )


@router.put("/live-trip/{share_code}/update")
async def update_live_trip(share_code: str, data: LiveTripUpdateRequest, db: Session = Depends(get_db)):
    """Update position for an active live trip (called by the driver's app every 5s)."""
    session = db.query(LiveTripSession).filter(
        LiveTripSession.share_code == share_code,
        LiveTripSession.is_active == True
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Live session not found")

    session.latitude = data.latitude
    session.longitude = data.longitude
    session.speed_kph = data.speed_kph
    session.risk_level = data.risk_level
    session.alert_level = data.alert_level
    session.last_updated = datetime.now(timezone.utc)
    db.commit()
    return {"status": "updated", "share_code": share_code}


@router.post("/live-trip/{share_code}/stop")
async def stop_live_trip(share_code: str, db: Session = Depends(get_db)):
    """Stop broadcasting a live trip."""
    session = db.query(LiveTripSession).filter(
        LiveTripSession.share_code == share_code,
        LiveTripSession.is_active == True
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Live session not found")
    session.is_active = False
    db.commit()
    return {"status": "stopped", "share_code": share_code}


@router.get("/live-trip/{share_code}", response_model=LiveTripResponse)
async def get_live_trip(share_code: str, db: Session = Depends(get_db)):
    """Get current live trip data (called by watchers polling every 5s)."""
    session = db.query(LiveTripSession).filter(
        LiveTripSession.share_code == share_code
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Live session not found")

    user = db.query(User).filter(User.id == session.user_id).first()

    # Increment watcher count (rough — doesn't deduplicate, but fine for MVP)
    session.watcher_count = (session.watcher_count or 0) + 1
    db.commit()

    return LiveTripResponse(
        id=session.id, user_id=session.user_id,
        user_name=user.name if user else "",
        trip_id=session.trip_id, share_code=session.share_code,
        is_active=session.is_active,
        latitude=session.latitude, longitude=session.longitude,
        speed_kph=session.speed_kph,
        risk_level=session.risk_level, alert_level=session.alert_level,
        watcher_count=session.watcher_count,
        last_updated=str(session.last_updated),
        created_at=str(session.created_at),
    )


# ─── Quick Hazard Alerts ─────────────────────────────────────────────────

@router.post("/quick-alert", response_model=QuickAlertResponse)
async def submit_quick_alert(data: QuickAlertCreate, db: Session = Depends(get_db)):
    """Submit a one-tap hazard alert. Auto-expires after 30 minutes."""
    alert = QuickHazardAlert(
        user_id=data.user_id,
        alert_type=data.alert_type,
        latitude=data.latitude,
        longitude=data.longitude,
        speed_at_report=data.speed_at_report,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    user = db.query(User).filter(User.id == data.user_id).first()
    return QuickAlertResponse(
        id=alert.id, user_id=alert.user_id,
        user_name=user.name if user else "",
        alert_type=alert.alert_type,
        latitude=alert.latitude, longitude=alert.longitude,
        speed_at_report=alert.speed_at_report,
        upvote_count=0,
        created_at=str(alert.created_at),
        expires_at=str(alert.expires_at),
    )


@router.get("/quick-alerts/nearby", response_model=QuickAlertsNearbyResponse)
async def get_nearby_quick_alerts(
    lat: float, lon: float, radius_km: float = 5.0,
    db: Session = Depends(get_db)
):
    """Get active quick hazard alerts within a radius."""
    now = datetime.now(timezone.utc)
    alerts = db.query(QuickHazardAlert).filter(
        QuickHazardAlert.is_active == True,
        QuickHazardAlert.expires_at > now,
        QuickHazardAlert.latitude.between(lat - 0.05, lat + 0.05),
        QuickHazardAlert.longitude.between(lon - 0.05, lon + 0.05),
    ).all()

    nearby = []
    for a in alerts:
        dist = _haversine(lat, lon, a.latitude, a.longitude)
        if dist <= radius_km:
            user = db.query(User).filter(User.id == a.user_id).first()
            nearby.append(QuickAlertResponse(
                id=a.id, user_id=a.user_id,
                user_name=user.name if user else "",
                alert_type=a.alert_type,
                latitude=a.latitude, longitude=a.longitude,
                speed_at_report=a.speed_at_report,
                upvote_count=a.upvote_count,
                distance_km=round(dist, 2),
                created_at=str(a.created_at),
                expires_at=str(a.expires_at) if a.expires_at else None,
            ))

    nearby.sort(key=lambda x: x.distance_km)
    return QuickAlertsNearbyResponse(count=len(nearby), alerts=nearby)


@router.post("/quick-alert/{alert_id}/upvote")
async def upvote_quick_alert(alert_id: int, db: Session = Depends(get_db)):
    """Upvote/confirm a hazard alert. Extends expiry by 15 minutes."""
    alert = db.query(QuickHazardAlert).filter(QuickHazardAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.upvote_count = (alert.upvote_count or 0) + 1
    # Each upvote extends the alert's lifetime by 15 minutes
    if alert.expires_at:
        alert.expires_at = alert.expires_at + timedelta(minutes=15)
    db.commit()
    return {"status": "upvoted", "upvote_count": alert.upvote_count}


# ─── Ride Groups (WheelSafar-Inspired) ───────────────────────────────────

@router.post("/groups", response_model=RideGroupResponse)
async def create_ride_group(
    user_id: str, data: RideGroupCreate, db: Session = Depends(get_db)
):
    """Create a new Ride Group and add the creator as ADMIN."""
    import uuid
    invite_code = uuid.uuid4().hex[:6].upper()

    group = RideGroup(
        name=data.name,
        description=data.description,
        invite_code=invite_code,
        creator_id=user_id
    )
    db.add(group)
    db.commit()
    db.refresh(group)

    member = GroupMember(
        group_id=group.id,
        user_id=user_id,
        role="ADMIN",
        status="JOINED"
    )
    db.add(member)
    db.commit()

    return await get_group_details(group.id, db)

@router.get("/debug/groups/{user_id}")
async def debug_groups(user_id: str, db: Session = Depends(get_db)):
    """Debug endpoint to see what groups exist and who belongs to them."""
    all_groups = db.query(RideGroup).all()
    all_members = db.query(GroupMember).all()
    all_users = db.query(User).all()

    debug_info = {
        "user_id_querying": user_id,
        "all_groups": [
            {
                "id": g.id,
                "name": g.name,
                "creator_id": g.creator_id,
                "invite_code": g.invite_code,
                "created_at": str(g.created_at)
            }
            for g in all_groups
        ],
        "all_members": [
            {
                "group_id": m.group_id,
                "user_id": m.user_id,
                "role": m.role,
                "status": m.status
            }
            for m in all_members
        ],
        "all_users": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email
            }
            for u in all_users
        ],
        "user_groups_memberships": [
            m.group_id for m in db.query(GroupMember).filter(GroupMember.user_id == user_id).all()
        ]
    }
    return debug_info

@router.get("/groups/user/{user_id}", response_model=list[RideGroupResponse])
async def get_user_groups(user_id: str, db: Session = Depends(get_db)):
    """Get all groups a user belongs to (as member or creator)."""
    from sqlalchemy import or_

    logger.debug(f"Fetching groups for user: {user_id}")

    memberships = db.query(GroupMember).filter(GroupMember.user_id == user_id).all()
    group_ids = [m.group_id for m in memberships]
    logger.debug(f"User {user_id} has {len(memberships)} memberships: group_ids={group_ids}")

    if group_ids:
        groups = db.query(RideGroup).filter(
            or_(
                RideGroup.id.in_(group_ids),
                RideGroup.creator_id == user_id
            )
        ).all()
    else:
        groups = db.query(RideGroup).filter(RideGroup.creator_id == user_id).all()

    logger.debug(f"Found {len(groups)} groups for user {user_id}")
    for g in groups:
        logger.debug(f"  Group {g.id}: {g.name} (creator_id={g.creator_id})")

    results = []
    for g in groups:
        results.append(await get_group_details(g.id, db))
    return results

@router.post("/groups/join", response_model=RideGroupResponse)
async def join_group(
    user_id: str, data: RideGroupJoin, db: Session = Depends(get_db)
):
    """Join a group using an invite code."""
    group = db.query(RideGroup).filter(RideGroup.invite_code == data.invite_code).first()
    if not group:
        raise HTTPException(status_code=404, detail="Invalid invite code or group not found")
        
    existing = db.query(GroupMember).filter(
        GroupMember.group_id == group.id, 
        GroupMember.user_id == user_id
    ).first()
    
    if existing:
        if existing.status == "INVITED":
            existing.status = "JOINED"
            db.commit()
    else:
        member = GroupMember(
            group_id=group.id,
            user_id=user_id,
            role="MEMBER",
            status="JOINED"
        )
        db.add(member)
        db.commit()

    return await get_group_details(group.id, db)

@router.get("/groups/{group_id}", response_model=RideGroupResponse)
async def get_group_details(group_id: int, db: Session = Depends(get_db)):
    """Get group details including members."""
    group = db.query(RideGroup).filter(RideGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
        
    members = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
    member_responses = []
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        member_responses.append(GroupMemberResponse(
            id=m.id,
            group_id=m.group_id,
            user_id=m.user_id,
            user_name=user.name if user else "Unknown User",
            role=m.role,
            status=m.status,
            joined_at=str(m.joined_at)
        ))
        
    return RideGroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        invite_code=group.invite_code,
        created_at=str(group.created_at),
        members=member_responses
    )

@router.get("/groups/{group_id}/live", response_model=GroupLiveLocationResponse)
async def get_group_live_locations(group_id: int, db: Session = Depends(get_db)):
    """Get active live locations for all members of a group."""
    group = db.query(RideGroup).filter(RideGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
        
    memberships = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.status == "JOINED"
    ).all()
    user_ids = [m.user_id for m in memberships]
    
    active_sessions = db.query(LiveTripSession).filter(
        LiveTripSession.user_id.in_(user_ids),
        LiveTripSession.is_active == True
    ).all()
    
    active_responses = []
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    for session in active_sessions:
        # Check if updated in last 5 minutes
        if not session.last_updated or now_naive - session.last_updated > timedelta(minutes=5):
            session.is_active = False
            db.commit()
            continue
            
        user = db.query(User).filter(User.id == session.user_id).first()
        active_responses.append(LiveTripResponse(
            id=session.id, user_id=session.user_id,
            user_name=user.name if user else "",
            trip_id=session.trip_id, share_code=session.share_code,
            is_active=session.is_active,
            latitude=session.latitude, longitude=session.longitude,
            speed_kph=session.speed_kph,
            risk_level=session.risk_level, alert_level=session.alert_level,
            watcher_count=session.watcher_count,
            last_updated=str(session.last_updated),
            created_at=str(session.created_at)
        ))
        
    return GroupLiveLocationResponse(
        group_id=group.id,
        group_name=group.name,
        active_members=active_responses
    )

# ─── Telematics (IMU) ───────────────────────────────────────────────────

@router.post("/trips/{trip_id}/telematics-event")
async def log_telematics_event(trip_id: str, request: TelematicsEventRequest, db: Session = Depends(get_db)):
    """Log a harsh driving event (hard braking, harsh cornering) to the trip."""
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    if request.event_type == "hard_brake":
        trip.hard_brake_count += 1
    elif request.event_type == "harsh_corner":
        trip.harsh_corner_count += 1
    else:
        raise HTTPException(status_code=400, detail="Invalid event type")

    db.commit()
    return {"status": "success", "event_type": request.event_type, "count": trip.hard_brake_count if request.event_type == "hard_brake" else trip.harsh_corner_count}


# ─── Emergency SOS ────────────────────────────────────────────────────────

@router.post("/emergency-sos", response_model=EmergencySOSResponse)
async def trigger_emergency_sos(request: EmergencySOSRequest, db: Session = Depends(get_db)):
    """
    Handle an automated SOS alert triggered by crash detection.
    Fetches emergency contacts and simulates notification.
    """
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = db.query(EmergencyProfile).filter(EmergencyProfile.user_id == user.id).first()
    
    # We always respond successfully to the mobile app, but log if profile is missing
    notified_contacts = []
    if profile:
        if profile.emergency_contact_1_phone:
            notified_contacts.append(f"{profile.emergency_contact_1_name or 'Primary Contact'} ({profile.emergency_contact_1_phone})")
        if profile.emergency_contact_2_phone:
            notified_contacts.append(f"{profile.emergency_contact_2_name or 'Secondary Contact'} ({profile.emergency_contact_2_phone})")
    
    # Logic for real SMS/Email would go here
    event_id = str(random.randint(100000, 999999))
    logger.critical(
        f"🚨 EMERGENCY SOS TRIGGERED! 🚨\n"
        f"User: {user.name} ({user.id})\n"
        f"Location: {request.latitude}, {request.longitude}\n"
        f"Risk at Impact: {request.risk_snapshot}\n"
        f"Speed: {request.speed_kph} km/h\n"
        f"Notified Contacts: {notified_contacts}"
    )

    # Trigger a persistent notification for the system/followers
    sos_notif = Notification(
        user_id=user.id,
        type="system",
        title="Emergency SOS Triggered!",
        message=f"Crash detected at {request.latitude}, {request.longitude}. Emergency contacts notified.",
        extra_data={"latitude": request.latitude, "longitude": request.longitude, "event_id": event_id}
    )
    db.add(sos_notif)
    db.commit()

    return EmergencySOSResponse(
        status="SOS_SENT",
        event_id=event_id,
        notified_contacts=notified_contacts,
        timestamp=str(datetime.now(timezone.utc)),
        latitude=request.latitude,
        longitude=request.longitude
    )


# ─── Digital Wallet ──────────────────────────────────────────────────────

@router.get("/wallet/{user_id}", response_model=WalletResponse)
async def get_wallet(user_id: str, db: Session = Depends(get_db)):
    """Get a user's digital wallet details."""
    wallet = db.query(DigitalWallet).filter(DigitalWallet.user_id == user_id).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return WalletResponse(
        user_id=wallet.user_id,
        license_no=wallet.license_no,
        vehicle_classes=wallet.vehicle_classes,
        license_dob=wallet.license_dob,
        blood_grp=wallet.blood_grp,
        issue_date=wallet.issue_date,
        expiry_date=wallet.expiry_date,
        license_pdf_url=wallet.license_pdf_url,
        nic_name=wallet.nic_name,
        nic_no=wallet.nic_no,
        nic_gender=wallet.nic_gender,
        nic_pob=wallet.nic_pob,
        nic_pdf_url=wallet.nic_pdf_url,
        updated_at=str(wallet.updated_at)
    )


@router.put("/wallet/{user_id}", response_model=WalletResponse)
async def upsert_wallet(user_id: str, data: WalletCreate, db: Session = Depends(get_db)):
    """Create or update a user's digital wallet."""
    wallet = db.query(DigitalWallet).filter(DigitalWallet.user_id == user_id).first()
    if wallet:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(wallet, field, value)
    else:
        wallet = DigitalWallet(user_id=user_id, **data.model_dump())
        db.add(wallet)
    
    db.commit()
    db.refresh(wallet)
    return WalletResponse(
        user_id=wallet.user_id,
        license_no=wallet.license_no,
        vehicle_classes=wallet.vehicle_classes,
        license_dob=wallet.license_dob,
        blood_grp=wallet.blood_grp,
        issue_date=wallet.issue_date,
        expiry_date=wallet.expiry_date,
        license_pdf_url=wallet.license_pdf_url,
        nic_name=wallet.nic_name,
        nic_no=wallet.nic_no,
        nic_gender=wallet.nic_gender,
        nic_pob=wallet.nic_pob,
        nic_pdf_url=wallet.nic_pdf_url,
        updated_at=str(wallet.updated_at)
    )


# ─── Convoy & Group Announcements ──────────────────────────────────────────

@router.post("/groups/{group_id}/convoy/start", response_model=RideGroupResponse)
async def start_convoy_session(group_id: int, request: ConvoyStartRequest, db: Session = Depends(get_db)):
    """Start a convoy session for a ride group, specifying a shared destination."""
    group = db.query(RideGroup).filter(RideGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Ride group not found")
        
    group.convoy_active = True
    group.destination_lat = request.destination_lat
    group.destination_lon = request.destination_lon
    group.destination_name = request.destination_name
    group.convoy_started_at = datetime.now(timezone.utc)
    
    # Broadcast a system announcement about the convoy start
    announcement = GroupAnnouncement(
        group_id=group_id,
        sender_id="system",
        sender_name="System",
        message=f"Convoy session started to {request.destination_name}!",
        announcement_type="system"
    )
    db.add(announcement)
    
    db.commit()
    db.refresh(group)
    return await get_group_details(group_id, db)


@router.post("/groups/{group_id}/convoy/stop", response_model=RideGroupResponse)
async def stop_convoy_session(group_id: int, db: Session = Depends(get_db)):
    """Stop the active convoy session for a ride group."""
    group = db.query(RideGroup).filter(RideGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Ride group not found")
        
    group.convoy_active = False
    group.destination_lat = None
    group.destination_lon = None
    group.destination_name = None
    group.convoy_started_at = None
    
    # Broadcast a system announcement about the convoy stop
    announcement = GroupAnnouncement(
        group_id=group_id,
        sender_id="system",
        sender_name="System",
        message="Convoy session has ended.",
        announcement_type="system"
    )
    db.add(announcement)
    
    db.commit()
    db.refresh(group)
    return await get_group_details(group_id, db)


@router.post("/groups/{group_id}/announcements", response_model=GroupAnnouncementResponse)
async def post_group_announcement(group_id: int, request: AnnouncementCreateRequest, db: Session = Depends(get_db)):
    """Post a walkie-talkie quick alert or text announcement to a ride group."""
    group = db.query(RideGroup).filter(RideGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Ride group not found")
        
    sender_name = "System"
    if request.sender_id != "system":
        user = db.query(User).filter(User.id == request.sender_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Sender not found")
        sender_name = user.name
        
    announcement = GroupAnnouncement(
        group_id=group_id,
        sender_id=request.sender_id,
        sender_name=sender_name,
        message=request.message,
        announcement_type=request.announcement_type
    )
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    
    return GroupAnnouncementResponse(
        id=announcement.id,
        group_id=announcement.group_id,
        sender_id=announcement.sender_id,
        sender_name=announcement.sender_name,
        message=announcement.message,
        announcement_type=announcement.announcement_type,
        created_at=str(announcement.created_at)
    )


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate the haversine distance between two points in km."""
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


@router.get("/groups/{group_id}/convoy/live", response_model=ConvoyLiveDetailsResponse)
async def get_convoy_live_details(group_id: int, db: Session = Depends(get_db)):
    """Get real-time details for an active convoy, including coordinates, remaining distance, Lead Car indicator, and route deviation states."""
    group = db.query(RideGroup).filter(RideGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Ride group not found")
        
    # Fetch all group members
    memberships = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.status == "JOINED"
    ).all()
    user_ids = [m.user_id for m in memberships]
    
    # Fetch active live sessions for members
    active_sessions = db.query(LiveTripSession).filter(
        LiveTripSession.user_id.in_(user_ids),
        LiveTripSession.is_active == True
    ).all()
    
    active_member_details = []
    
    # Check if sessions are active (within last 5 minutes)
    valid_sessions = []
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    for s in active_sessions:
        if not s.last_updated or now_naive - s.last_updated > timedelta(minutes=5):
            s.is_active = False
            db.commit()
            continue
        valid_sessions.append(s)
        
    # Compute distance to destination if convoy is active
    for s in valid_sessions:
        user = db.query(User).filter(User.id == s.user_id).first()
        dist = None
        is_off_route = False
        
        if group.convoy_active and group.destination_lat is not None and s.latitude is not None:
            dist = haversine_distance(s.latitude, s.longitude, group.destination_lat, group.destination_lon)
            
        active_member_details.append({
            "session": s,
            "user_name": user.name if user else "Driver",
            "distance_remaining_km": dist,
            "is_off_route": is_off_route
        })
        
    # Sort active members by proximity to destination to determine Lead Car (closest first)
    if group.convoy_active and active_member_details:
        dist_members = [m for m in active_member_details if m["distance_remaining_km"] is not None]
        dist_members.sort(key=lambda x: x["distance_remaining_km"])
        
        if dist_members:
            lead_user_id = dist_members[0]["session"].user_id
            for m in active_member_details:
                if m["session"].user_id == lead_user_id:
                    m["is_lead"] = True
                    
                    # 🛡️ Cooperative Alert Propagation:
                    # If the Lead Car's alert level is 'RED', auto-broadcast a hazard announcement to the group
                    lead_session = m["session"]
                    if lead_session.alert_level == "RED":
                        last_scout = db.query(GroupAnnouncement).filter(
                            GroupAnnouncement.group_id == group_id,
                            GroupAnnouncement.announcement_type == "hazard_scout"
                        ).order_by(GroupAnnouncement.created_at.desc()).first()
                        
                        should_broadcast = True
                        if last_scout:
                            now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
                            if last_scout.created_at:
                                diff = now_naive - last_scout.created_at
                                if diff.total_seconds() < 60:
                                    should_broadcast = False
                                
                        if should_broadcast:
                            scout_announcement = GroupAnnouncement(
                                group_id=group_id,
                                sender_id="system",
                                sender_name="Lead Car Scout",
                                message=f"Caution! Lead car {m['user_name']} reports high risk hazard ahead!",
                                announcement_type="hazard_scout"
                            )
                            db.add(scout_announcement)
                            db.commit()
    
    # Map to schema response
    member_responses = []
    for m in active_member_details:
        s = m["session"]
        member_responses.append(ConvoyMemberDetails(
            user_id=s.user_id,
            user_name=m["user_name"],
            latitude=s.latitude,
            longitude=s.longitude,
            speed_kph=s.speed_kph,
            risk_level=s.risk_level,
            alert_level=s.alert_level,
            last_updated=str(s.last_updated),
            distance_remaining_km=m["distance_remaining_km"],
            is_active=s.is_active,
            is_lead=m.get("is_lead", False),
            is_off_route=m["is_off_route"]
        ))
        
    # Fetch last 10 announcements
    announcements = db.query(GroupAnnouncement).filter(
        GroupAnnouncement.group_id == group_id
    ).order_by(GroupAnnouncement.created_at.desc()).limit(10).all()
    announcements.reverse()
    
    announcement_responses = [
        GroupAnnouncementResponse(
            id=a.id,
            group_id=a.group_id,
            sender_id=a.sender_id,
            sender_name=a.sender_name,
            message=a.message,
            announcement_type=a.announcement_type,
            created_at=str(a.created_at)
        )
        for a in announcements
    ]
    
    # ── Check and Resolve Expired Polls ──
    now = datetime.now(timezone.utc)
    expired_polls = db.query(ConvoyPoll).filter(
        ConvoyPoll.group_id == group_id,
        ConvoyPoll.status == "active",
        ConvoyPoll.expires_at < now
    ).all()

    for p in expired_polls:
        votes = db.query(ConvoyPollVote).filter(ConvoyPollVote.poll_id == p.id).all()
        yes_count = sum(1 for v in votes if v.vote == "yes")
        no_count = sum(1 for v in votes if v.vote == "no")
        
        if yes_count > no_count and yes_count > 0:
            p.status = "accepted"
            announcement = GroupAnnouncement(
                group_id=group_id,
                sender_id="system",
                sender_name="System",
                message=f"Shared stop '{p.option_name}' approved after timeout!",
                announcement_type="system"
            )
            db.add(announcement)
        else:
            p.status = "rejected"
            announcement = GroupAnnouncement(
                group_id=group_id,
                sender_id="system",
                sender_name="System",
                message=f"Shared stop proposal '{p.option_name}' timed out and rejected.",
                announcement_type="system"
            )
            db.add(announcement)
    if expired_polls:
        db.commit()

    # Fetch recent/active polls
    recent_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=15)
    polls = db.query(ConvoyPoll).filter(
        ConvoyPoll.group_id == group_id,
        (ConvoyPoll.status == "active") | (ConvoyPoll.created_at > recent_time)
    ).all()

    poll_responses = []
    for p in polls:
        p_votes = db.query(ConvoyPollVote).filter(ConvoyPollVote.poll_id == p.id).all()
        yes_voters = [v.user_name for v in p_votes if v.vote == "yes"]
        no_voters = [v.user_name for v in p_votes if v.vote == "no"]
        
        poll_responses.append(ConvoyPollResponse(
            id=p.id,
            group_id=p.group_id,
            creator_id=p.creator_id,
            creator_name=p.creator_name,
            poll_type=p.poll_type,
            option_name=p.option_name,
            latitude=p.latitude,
            longitude=p.longitude,
            status=p.status,
            yes_votes=yes_voters,
            no_votes=no_voters,
            created_at=str(p.created_at),
            expires_at=str(p.expires_at)
        ))

    return ConvoyLiveDetailsResponse(
        group_id=group.id,
        group_name=group.name,
        convoy_active=group.convoy_active,
        destination_lat=group.destination_lat,
        destination_lon=group.destination_lon,
        destination_name=group.destination_name,
        active_members=member_responses,
        announcements=announcement_responses,
        active_polls=poll_responses
    )


@router.post("/groups/{group_id}/polls", response_model=ConvoyPollResponse)
async def create_convoy_poll(group_id: int, request: ConvoyPollCreateRequest, db: Session = Depends(get_db)):
    """Create a new rest/fuel stop poll inside a convoy."""
    group = db.query(RideGroup).filter(RideGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    creator = db.query(User).filter(User.id == request.creator_id).first()
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")

    created_now = datetime.now(timezone.utc)
    expires_at = created_now + timedelta(minutes=3)

    poll = ConvoyPoll(
        group_id=group_id,
        creator_id=request.creator_id,
        creator_name=creator.name,
        poll_type=request.poll_type,
        option_name=request.option_name,
        latitude=request.latitude,
        longitude=request.longitude,
        status="active",
        created_at=created_now,
        expires_at=expires_at
    )
    db.add(poll)
    db.commit()
    db.refresh(poll)

    vote = ConvoyPollVote(
        poll_id=poll.id,
        user_id=request.creator_id,
        user_name=creator.name,
        vote="yes",
        created_at=created_now
    )
    db.add(vote)
    
    announcement = GroupAnnouncement(
        group_id=group_id,
        sender_id="system",
        sender_name="System",
        message=f"{creator.name} proposed a {request.poll_type} stop: {request.option_name}",
        announcement_type="system"
    )
    db.add(announcement)
    db.commit()
    db.refresh(poll)

    return ConvoyPollResponse(
        id=poll.id,
        group_id=poll.group_id,
        creator_id=poll.creator_id,
        creator_name=poll.creator_name,
        poll_type=poll.poll_type,
        option_name=poll.option_name,
        latitude=poll.latitude,
        longitude=poll.longitude,
        status=poll.status,
        yes_votes=[creator.name],
        no_votes=[],
        created_at=str(poll.created_at),
        expires_at=str(poll.expires_at)
    )


@router.post("/groups/{group_id}/polls/{poll_id}/vote", response_model=ConvoyPollResponse)
async def vote_convoy_poll(group_id: int, poll_id: int, request: ConvoyPollVoteRequest, db: Session = Depends(get_db)):
    """Vote 'yes' or 'no' on a convoy poll."""
    poll = db.query(ConvoyPoll).filter(ConvoyPoll.id == poll_id, ConvoyPoll.group_id == group_id).first()
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    if poll.status != "active" or (poll.expires_at and now_naive > poll.expires_at):
        raise HTTPException(status_code=400, detail="Poll is no longer active")

    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    existing_vote = db.query(ConvoyPollVote).filter(
        ConvoyPollVote.poll_id == poll_id,
        ConvoyPollVote.user_id == request.user_id
    ).first()

    if existing_vote:
        existing_vote.vote = request.vote
        existing_vote.created_at = datetime.now(timezone.utc)
    else:
        new_vote = ConvoyPollVote(
            poll_id=poll_id,
            user_id=request.user_id,
            user_name=user.name,
            vote=request.vote
        )
        db.add(new_vote)

    db.commit()
    db.refresh(poll)

    votes = db.query(ConvoyPollVote).filter(ConvoyPollVote.poll_id == poll_id).all()
    yes_votes = [v.user_name for v in votes if v.vote == "yes"]
    no_votes = [v.user_name for v in votes if v.vote == "no"]

    memberships = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.status == "JOINED"
    ).all()
    user_ids = [m.user_id for m in memberships]
    
    active_driving_count = db.query(LiveTripSession).filter(
        LiveTripSession.user_id.in_(user_ids),
        LiveTripSession.is_active == True,
        LiveTripSession.last_updated > datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    ).count()

    total_voters = active_driving_count if active_driving_count > 0 else len(user_ids)
    majority_threshold = (total_voters / 2) + 0.01

    if len(yes_votes) >= majority_threshold:
        poll.status = "accepted"
        announcement = GroupAnnouncement(
            group_id=group_id,
            sender_id="system",
            sender_name="System",
            message=f"Shared stop '{poll.option_name}' approved by majority!",
            announcement_type="system"
        )
        db.add(announcement)
    elif len(no_votes) >= majority_threshold or (len(yes_votes) + len(no_votes) == total_voters and len(yes_votes) < len(no_votes)):
        poll.status = "rejected"
        announcement = GroupAnnouncement(
            group_id=group_id,
            sender_id="system",
            sender_name="System",
            message=f"Shared stop proposal '{poll.option_name}' was rejected.",
            announcement_type="system"
        )
        db.add(announcement)

    db.commit()
    db.refresh(poll)

    return ConvoyPollResponse(
        id=poll.id,
        group_id=poll.group_id,
        creator_id=poll.creator_id,
        creator_name=poll.creator_name,
        poll_type=poll.poll_type,
        option_name=poll.option_name,
        latitude=poll.latitude,
        longitude=poll.longitude,
        status=poll.status,
        yes_votes=yes_votes,
        no_votes=no_votes,
        created_at=str(poll.created_at),
        expires_at=str(poll.expires_at)
    )

