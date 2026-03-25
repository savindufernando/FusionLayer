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
import logging
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .models import (
    User, Vehicle, Trip, TelemetryPoint,
    CrowdsourcedSign, BlackspotReport, InsuranceClaim, AccidentReport,
    PermanentHotspot
)
from .schemas import (
    MobileAnalyzeRequest, MobileAnalyzeResponse,
    UserCreate, UserResponse,
    VehicleCreate, VehicleResponse,
    TripResponse, TripListResponse,
    BlackspotCreate, BlackspotResponse,
    InsuranceClaimCreate, InsuranceClaimResponse,
    HotspotItem, HotspotsListResponse,
    AccidentReportCreate, AccidentReportResponse
)
from .circuit_breaker import CircuitBreaker

from src.fusion_engine import FusionEngine, TSRInput, DZInput, HotspotInput


logger = logging.getLogger("mobile_api")

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

    # ─── Call Fusion Engine ──────────────────────────────────────
    degraded = False
    tsr_url = _config.get("tsr_url", "http://localhost:8001")
    tsr_endpoint = _config.get("tsr_endpoint", "/api/predict/base64")
    dz_url = _config.get("dz_url", "http://localhost:8000")
    dz_endpoint = _config.get("dz_endpoint", "/api/predict")

    headers = {"x-api-key": os.getenv("DG_API_KEY", "")}
    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        # ── Call DZ Module ───────────────────────────────────
        dz = None
        if _cb_dz.can_execute():
            try:
                dz_resp = await client.post(
                    f"{dz_url}{dz_endpoint}",
                    json={
                        "latitude": request.latitude,
                        "longitude": request.longitude,
                        "heading": request.heading,
                        "speed_kph": request.speed_kph,
                        "scenario": "auto"
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

        # DZ fallback
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

        # ── Call TSR Module (only if camera frame is provided) ──
        tsr = None
        if request.image_base64 and _cb_tsr.can_execute():
            try:
                tsr_resp = await client.post(
                    f"{tsr_url}{tsr_endpoint}",
                    json={"image": request.image_base64}
                )
                tsr_data = tsr_resp.json()
                tsr = TSRInput(
                    class_id=tsr_data.get("class_id", 0),
                    class_name=tsr_data.get("class_name", "unknown"),
                    confidence=tsr_data.get("confidence", 0),
                    is_confident=tsr_data.get("is_confident", False),
                    latitude=request.latitude,
                    longitude=request.longitude
                )
                _cb_tsr.record_success()

                # ── TSR Virtualization: Save detected sign to cloud map ──
                if tsr.confidence >= 0.85:
                    _save_crowdsourced_sign(db, tsr, request.latitude, request.longitude)
            except Exception as e:
                _cb_tsr.record_failure()
                logger.warning(f"TSR module call failed: {e}")
                degraded = True
        elif not request.image_base64:
            # ── TSR Virtualization: Check cloud sign map for this location ──
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

    # ── Store telemetry point ────────────────────────────────
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

    db.commit()

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

@router.post("/users", response_model=UserResponse)
async def create_user(data: UserCreate, db: Session = Depends(get_db)):
    """Register a new DriveGuard user."""
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(name=data.name, email=data.email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse(
        id=user.id, name=user.name, email=user.email,
        created_at=str(user.created_at), vehicle_count=0
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, db: Session = Depends(get_db)):
    """Get user profile."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(
        id=user.id, name=user.name, email=user.email,
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
        led_stick_mac=data.led_stick_mac
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return VehicleResponse(
        id=vehicle.id, user_id=vehicle.user_id,
        make_model=vehicle.make_model, vehicle_type=vehicle.vehicle_type,
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
            led_stick_mac=v.led_stick_mac,
            created_at=str(v.created_at),
            trip_count=len(v.trips)
        )
        for v in vehicles
    ]


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
                point_count=t.point_count
            )
            for t in trips
        ]
    )


@router.post("/trips/{trip_id}/end")
async def end_trip(trip_id: str, db: Session = Depends(get_db)):
    """End an active trip."""
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.is_active == True).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Active trip not found")
    trip.is_active = False
    trip.end_time = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ended", "trip_id": trip.id, "avg_risk": round(trip.avg_risk_score, 1)}


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
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2)
    )
    db.add(report)
    db.commit()
    db.refresh(report)
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
