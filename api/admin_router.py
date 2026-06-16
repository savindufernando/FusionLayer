from fastapi import APIRouter, Depends, HTTPException, Query, Body, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional, Any, Dict
from pydantic import BaseModel
import os

from .database import get_db
from .models import (
    User, Vehicle, Trip, TelemetryPoint, CrowdsourcedSign,
    BlackspotReport, InsuranceClaim, AccidentReport, PermanentHotspot,
    AdminUser, EmergencyProfile, CommunityPost, UserStatusItem,
    RideGroup, SharedRoute, DrivingChallenge, DigitalWallet,
    LiveTripSession, QuickHazardAlert
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# --- Admin Auth ---

class AdminLoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
def admin_login(req: AdminLoginRequest, db: Session = Depends(get_db)):
    admin = db.query(AdminUser).filter(
        AdminUser.username == req.username.strip(),
        AdminUser.password == req.password.strip()
    ).first()
    
    if admin:
        return {"access_token": "admin_mock_token_xyz123", "token_type": "bearer"}
    
    raise HTTPException(status_code=401, detail="Invalid admin credentials")


# --- Admin Dashboard Stats ---

@router.get("/stats")
def get_admin_stats(db: Session = Depends(get_db)):
    total_users = db.query(User).count()
    total_vehicles = db.query(Vehicle).count()
    total_trips = db.query(Trip).count()
    active_trips = db.query(Trip).filter(Trip.is_active == True).count()
    total_reports = db.query(BlackspotReport).count()
    total_hotspots = db.query(PermanentHotspot).count()
    
    return {
        "total_users": total_users,
        "total_vehicles": total_vehicles,
        "total_trips": total_trips,
        "active_trips": active_trips,
        "total_reports": total_reports,
        "total_hotspots": total_hotspots
    }


# --- Generic CRUD helpers ---

def get_paginated(db: Session, model, skip: int = 0, limit: int = 100):
    items = db.query(model).offset(skip).limit(limit).all()
    total = db.query(model).count()
    return {"items": items, "total": total}


# --- Users ---

@router.get("/users")
def get_users(search: Optional[str] = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    if search:
        query = db.query(User).filter(or_(User.name.ilike(f"%{search}%"), User.email.ilike(f"%{search}%")))
        total = query.count()
        items = query.offset(skip).limit(limit).all()
        return {"items": items, "total": total, "skip": skip, "limit": limit}
    return get_paginated(db, User, skip, limit)

@router.delete("/users/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"status": "success"}


# --- Vehicles ---

@router.get("/vehicles")
def get_vehicles(search: Optional[str] = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    if search:
        query = db.query(Vehicle).filter(or_(Vehicle.make_model.ilike(f"%{search}%"), Vehicle.registration_number.ilike(f"%{search}%")))
        total = query.count()
        items = query.offset(skip).limit(limit).all()
        return {"items": items, "total": total, "skip": skip, "limit": limit}
    return get_paginated(db, Vehicle, skip, limit)

@router.delete("/vehicles/{vehicle_id}")
def delete_vehicle(vehicle_id: str, db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    db.delete(vehicle)
    db.commit()
    return {"status": "success"}


# --- Trips ---

@router.get("/trips")
def get_trips(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_paginated(db, Trip, skip, limit)

@router.delete("/trips/{trip_id}")
def delete_trip(trip_id: str, db: Session = Depends(get_db)):
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    db.delete(trip)
    db.commit()
    return {"status": "success"}


# --- Blackspot Reports ---

@router.get("/reports/blackspots")
def get_blackspot_reports(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_paginated(db, BlackspotReport, skip, limit)

@router.delete("/reports/blackspots/{report_id}")
def delete_blackspot_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(BlackspotReport).filter(BlackspotReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    db.delete(report)
    db.commit()
    return {"status": "success"}


# --- Permanent Hotspots ---

@router.get("/hotspots")
def get_hotspots(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_paginated(db, PermanentHotspot, skip, limit)

@router.delete("/hotspots/{hotspot_id}")
def delete_hotspot(hotspot_id: int, db: Session = Depends(get_db)):
    hotspot = db.query(PermanentHotspot).filter(PermanentHotspot.id == hotspot_id).first()
    if not hotspot:
        raise HTTPException(status_code=404, detail="Hotspot not found")
    db.delete(hotspot)
    db.commit()
    return {"status": "success"}

@router.put("/hotspots/{hotspot_id}")
def update_hotspot(hotspot_id: int, data: dict = Body(...), db: Session = Depends(get_db)):
    hotspot = db.query(PermanentHotspot).filter(PermanentHotspot.id == hotspot_id).first()
    if not hotspot:
        raise HTTPException(status_code=404, detail="Hotspot not found")
    
    if "name" in data:
        hotspot.name = data["name"]
    if "risk_boost" in data:
        hotspot.risk_boost = data["risk_boost"]
    if "is_active" in data:
        hotspot.is_active = data["is_active"]
        
    db.commit()
    db.refresh(hotspot)
    return hotspot


# --- Accident Reports ---

@router.get("/reports/accidents")
def get_accident_reports(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_paginated(db, AccidentReport, skip, limit)

@router.delete("/reports/accidents/{report_id}")
def delete_accident_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(AccidentReport).filter(AccidentReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    db.delete(report)
    db.commit()
    return {"status": "success"}

# --- Additional Expanded Endpoints ---

@router.get("/emergency/profiles")
def get_emergency_profiles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_paginated(db, EmergencyProfile, skip, limit)

@router.get("/emergency/claims")
def get_insurance_claims(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_paginated(db, InsuranceClaim, skip, limit)

@router.delete("/emergency/claims/{claim_id}")
def delete_insurance_claim(claim_id: str, db: Session = Depends(get_db)):
    claim = db.query(InsuranceClaim).filter(InsuranceClaim.id == claim_id).first()
    if not claim: raise HTTPException(status_code=404, detail="Not found")
    db.delete(claim)
    db.commit()
    return {"status": "success"}

@router.get("/social/posts")
def get_community_posts(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_paginated(db, CommunityPost, skip, limit)

@router.delete("/social/posts/{post_id}")
def delete_community_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    if not post: raise HTTPException(status_code=404, detail="Not found")
    db.delete(post)
    db.commit()
    return {"status": "success"}

@router.get("/social/groups")
def get_ride_groups(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_paginated(db, RideGroup, skip, limit)

@router.delete("/social/groups/{group_id}")
def delete_ride_group(group_id: int, db: Session = Depends(get_db)):
    group = db.query(RideGroup).filter(RideGroup.id == group_id).first()
    if not group: raise HTTPException(status_code=404, detail="Not found")
    db.delete(group)
    db.commit()
    return {"status": "success"}

@router.get("/social/routes")
def get_shared_routes(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_paginated(db, SharedRoute, skip, limit)

@router.delete("/social/routes/{route_id}")
def delete_shared_route(route_id: int, db: Session = Depends(get_db)):
    route = db.query(SharedRoute).filter(SharedRoute.id == route_id).first()
    if not route: raise HTTPException(status_code=404, detail="Not found")
    db.delete(route)
    db.commit()
    return {"status": "success"}

@router.get("/gamification/challenges")
def get_driving_challenges(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_paginated(db, DrivingChallenge, skip, limit)

@router.delete("/gamification/challenges/{challenge_id}")
def delete_driving_challenge(challenge_id: int, db: Session = Depends(get_db)):
    challenge = db.query(DrivingChallenge).filter(DrivingChallenge.id == challenge_id).first()
    if not challenge: raise HTTPException(status_code=404, detail="Not found")
    db.delete(challenge)
    db.commit()
    return {"status": "success"}

@router.get("/gamification/wallets")
def get_digital_wallets(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_paginated(db, DigitalWallet, skip, limit)

@router.delete("/gamification/wallets/{user_id}")
def delete_digital_wallet(user_id: str, db: Session = Depends(get_db)):
    wallet = db.query(DigitalWallet).filter(DigitalWallet.user_id == user_id).first()
    if not wallet: raise HTTPException(status_code=404, detail="Not found")
    db.delete(wallet)
    db.commit()
    return {"status": "success"}

class PasswordChangeRequest(BaseModel):
    new_password: str

@router.post("/users/{user_id}/change-password")
def change_user_password(user_id: str, req: PasswordChangeRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    import bcrypt
    salt = bcrypt.gensalt()
    user.password_hash = bcrypt.hashpw(req.new_password.encode('utf-8'), salt).decode('utf-8')
    db.commit()
    return {"status": "success", "message": "Password changed successfully"}

@router.post("/users/{user_id}/reset-password-email")
def send_reset_password_email(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Mock Email Sending
    print("="*50)
    print(f"MOCK EMAIL SENT TO: {user.email}")
    print(f"SUBJECT: DriveGuard Password Reset")
    print(f"BODY: Hi {user.name}, click here to reset your password: https://driveguard.lk/reset?token=mock_token_123")
    print("="*50)
    
    return {"status": "success", "message": "Reset email sent successfully"}

@router.get("/users/{user_id}/export-data")
def export_user_data(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    export = {
        "profile": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "created_at": str(user.created_at),
            "safety_score": user.safety_score,
            "total_distance_km": user.total_distance_km,
            "gdpr_consent": user.gdpr_consent,
            "gdpr_consent_date": str(user.gdpr_consent_date) if user.gdpr_consent_date else None
        },
        "vehicles": [
            {
                "id": v.id,
                "make_model": v.make_model,
                "vehicle_type": v.vehicle_type,
                "created_at": str(v.created_at)
            } for v in user.vehicles
        ],
        "blackspot_reports": [
            {
                "id": r.id,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "description": r.description,
                "report_type": r.report_type,
                "created_at": str(r.created_at)
            } for r in user.blackspot_reports
        ],
        "insurance_claims": [
            {
                "id": c.id,
                "status": c.status,
                "latitude": c.latitude,
                "longitude": c.longitude,
                "created_at": str(c.created_at)
            } for c in user.insurance_claims
        ],
        "shared_posts": [
            {
                "id": p.id,
                "caption": p.caption,
                "created_at": str(p.created_at)
            } for p in user.shared_trips
        ]
    }
    
    return export

@router.get("/live/sessions")
def get_live_sessions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_paginated(db, LiveTripSession, skip, limit)

@router.delete("/live/sessions/{session_id}")
def delete_live_session(session_id: int, db: Session = Depends(get_db)):
    session = db.query(LiveTripSession).filter(LiveTripSession.id == session_id).first()
    if not session: raise HTTPException(status_code=404, detail="Not found")
    db.delete(session)
    db.commit()
    return {"status": "success"}

@router.get("/live/alerts")
def get_quick_alerts(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_paginated(db, QuickHazardAlert, skip, limit)

@router.delete("/live/alerts/{alert_id}")
def delete_quick_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(QuickHazardAlert).filter(QuickHazardAlert.id == alert_id).first()
    if not alert: raise HTTPException(status_code=404, detail="Not found")
    db.delete(alert)
    db.commit()
    return {"status": "success"}

@router.get("/live/tsr")
def get_tsr_signs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_paginated(db, CrowdsourcedSign, skip, limit)

@router.delete("/live/tsr/{sign_id}")
def delete_tsr_sign(sign_id: int, db: Session = Depends(get_db)):
    sign = db.query(CrowdsourcedSign).filter(CrowdsourcedSign.id == sign_id).first()
    if not sign: raise HTTPException(status_code=404, detail="Not found")
    db.delete(sign)
    db.commit()
    return {"status": "success"}

class CreateTSRRequest(BaseModel):
    class_name: str
    latitude: float
    longitude: float

@router.post("/live/tsr")
def create_tsr_direct(req: CreateTSRRequest, db: Session = Depends(get_db)):
    sign = CrowdsourcedSign(
        latitude=req.latitude,
        longitude=req.longitude,
        class_id=0,
        class_name=req.class_name,
        confidence=1.0,
        report_count=100
    )
    db.add(sign)
    db.commit()
    db.refresh(sign)
    return {"status": "success", "sign": {"id": sign.id, "lat": sign.latitude, "lon": sign.longitude}}

class TSRGeocodeSingleRequest(BaseModel):
    address: str
    class_name: str

@router.post("/live/tsr/geocode-single")
def create_tsr_from_address(req: TSRGeocodeSingleRequest, db: Session = Depends(get_db)):
    try:
        from geopy.geocoders import Nominatim
        import time
        geolocator = Nominatim(user_agent="driveguard_admin_tsr")
        location = geolocator.geocode(req.address)
        
        if not location:
            raise HTTPException(status_code=400, detail="Could not geocode the provided address.")
            
        sign = CrowdsourcedSign(
            latitude=location.latitude,
            longitude=location.longitude,
            class_id=0,
            class_name=req.class_name,
            confidence=1.0,
            report_count=100
        )
        db.add(sign)
        db.commit()
        db.refresh(sign)
        
        return {
            "status": "success",
            "message": f"Successfully geocoded and saved '{req.class_name}' at {location.latitude}, {location.longitude}",
            "sign": {
                "id": sign.id,
                "lat": sign.latitude,
                "lon": sign.longitude,
                "class_name": sign.class_name
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/live/tsr/bulk-upload")
async def bulk_upload_tsr(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(('.xlsx', '.csv')):
        raise HTTPException(status_code=400, detail="Only .xlsx and .csv files are supported")
        
    try:
        import pandas as pd
        import io
        from geopy.geocoders import Nominatim
        import time
        
        contents = await file.read()
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
            
        # Standardize column names
        df.columns = df.columns.str.lower().str.strip()
        
        success_count = 0
        failed_rows = []
        geolocator = Nominatim(user_agent="driveguard_admin_tsr_bulk")
        
        for index, row in df.iterrows():
            try:
                class_name = row.get("sign_type") or row.get("class_name") or "Unknown Sign"
                
                # If latitude and longitude exist, use them directly
                if "latitude" in row and "longitude" in row and pd.notna(row["latitude"]) and pd.notna(row["longitude"]):
                    sign = CrowdsourcedSign(
                        latitude=float(row["latitude"]),
                        longitude=float(row["longitude"]),
                        class_id=int(row.get("class_id", 0)) if pd.notna(row.get("class_id")) else 0,
                        class_name=str(class_name),
                        confidence=1.0,
                        report_count=100
                    )
                    db.add(sign)
                    success_count += 1
                
                # Otherwise, geocode the address
                elif "address" in row and pd.notna(row["address"]):
                    address = str(row["address"])
                    location = geolocator.geocode(address)
                    if location:
                        sign = CrowdsourcedSign(
                            latitude=location.latitude,
                            longitude=location.longitude,
                            class_id=int(row.get("class_id", 0)) if pd.notna(row.get("class_id")) else 0,
                            class_name=str(class_name),
                            confidence=1.0,
                            report_count=100
                        )
                        db.add(sign)
                        success_count += 1
                    else:
                        failed_rows.append(f"Row {index+1}: Geocoding failed for '{address}'")
                    
                    # Rate limit Nominatim
                    time.sleep(1.1)
                else:
                    failed_rows.append(f"Row {index+1}: Missing latitude/longitude or address")
                    
            except Exception as e:
                failed_rows.append(f"Row {index+1}: {str(e)}")
                
        db.commit()
        
        return {
            "status": "success",
            "message": f"Processed file. {success_count} inserted, {len(failed_rows)} failed.",
            "success_count": success_count,
            "failed_rows": failed_rows
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@router.get("/maps/all-blackspots")
def get_all_blackspots(db: Session = Depends(get_db)):
    reports = db.query(BlackspotReport).all()
    hotspots = db.query(PermanentHotspot).all()
    
    return {
        "user_reports": [
            {
                "id": r.id, "lat": r.latitude, "lon": r.longitude,
                "description": r.description, "type": r.report_type
            } for r in reports
        ],
        "permanent_hotspots": [
            {
                "id": h.id, "lat": h.latitude, "lon": h.longitude,
                "name": h.name, "risk_boost": h.risk_boost, "is_active": h.is_active
            } for h in hotspots
        ]
    }

# --- Geocoded Hotspot Creation ---
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import time
import pandas as pd
import io

geolocator = Nominatim(user_agent="driveguard_admin_portal")

class GeocodeSingleRequest(BaseModel):
    address: str
    risk_boost: float = 1.0

@router.post("/hotspots/geocode-single")
def create_hotspot_from_address(req: GeocodeSingleRequest, db: Session = Depends(get_db)):
    try:
        location = geolocator.geocode(req.address)
        if not location:
            raise HTTPException(status_code=400, detail="Address not found")
            
        hotspot = PermanentHotspot(
            latitude=location.latitude,
            longitude=location.longitude,
            name=req.address,
            risk_boost=req.risk_boost,
            is_active=True
        )
        db.add(hotspot)
        db.commit()
        db.refresh(hotspot)
        return {"status": "success", "hotspot_id": hotspot.id, "lat": hotspot.latitude, "lon": hotspot.longitude}
    except GeocoderTimedOut:
        raise HTTPException(status_code=503, detail="Geocoding service timed out")

@router.post("/hotspots/bulk-upload")
async def bulk_upload_hotspots(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(('.xlsx', '.csv')):
        raise HTTPException(status_code=400, detail="Only .xlsx or .csv files are supported")
        
    try:
        contents = await file.read()
        if file.filename.endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            df = pd.read_csv(io.BytesIO(contents))
            
        # Expected columns: 'address', 'risk_boost'
        # Fallbacks for case-insensitivity
        df.columns = [c.lower().strip() for c in df.columns]
        
        if 'address' not in df.columns:
            raise HTTPException(status_code=400, detail="Missing 'address' column in file")
            
        success_count = 0
        failed_addresses = []
        
        for index, row in df.iterrows():
            address = str(row['address'])
            if pd.isna(address) or not address.strip():
                continue
                
            risk_boost = float(row.get('risk_boost', 1.0)) if not pd.isna(row.get('risk_boost')) else 1.0
            
            try:
                location = geolocator.geocode(address)
                if location:
                    hotspot = PermanentHotspot(
                        latitude=location.latitude,
                        longitude=location.longitude,
                        name=address,
                        risk_boost=risk_boost,
                        is_active=True
                    )
                    db.add(hotspot)
                    success_count += 1
                else:
                    failed_addresses.append(address)
                
                # Respect Nominatim's 1 request/second limit
                time.sleep(1.1)
                
            except Exception as e:
                failed_addresses.append(f"{address} ({str(e)})")
                
        db.commit()
        
        return {
            "status": "success",
            "message": f"Processed file. {success_count} inserted, {len(failed_addresses)} failed.",
            "success_count": success_count,
            "failed_addresses": failed_addresses
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

class CreateHotspotRequest(BaseModel):
    name: str = "Map Selection"
    latitude: float
    longitude: float
    risk_boost: float = 1.0

@router.post("/hotspots")
def create_hotspot_direct(req: CreateHotspotRequest, db: Session = Depends(get_db)):
    hotspot = PermanentHotspot(
        latitude=req.latitude,
        longitude=req.longitude,
        name=req.name,
        risk_boost=req.risk_boost,
        is_active=True
    )
    db.add(hotspot)
    db.commit()
    db.refresh(hotspot)
    return {"status": "success", "hotspot": {"id": hotspot.id, "lat": hotspot.latitude, "lon": hotspot.longitude}}

