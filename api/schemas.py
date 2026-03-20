"""
Pydantic schemas for Fusion Layer API request/response validation.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from enum import Enum


class FusionRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# ─── Request Models ───────────────────────────────────────────────────────

class FusedPredictionRequest(BaseModel):
    """Request for fused risk prediction (GPS + optional camera frame)."""
    latitude: float = Field(..., ge=-90, le=90, description="GPS latitude")
    longitude: float = Field(..., ge=-180, le=180, description="GPS longitude")
    heading: float = Field(default=0.0, ge=0, le=360, description="Vehicle heading (degrees)")
    speed_kph: float = Field(default=40.0, ge=0, le=200, description="Vehicle speed (km/h)")
    scenario: str = Field(default="sunny", description="Weather scenario override")
    image_base64: Optional[str] = Field(default=None, description="Camera frame as base64 JPEG/PNG")
    
    class Config:
        json_schema_extra = {
            "example": {
                "latitude": 6.9271,
                "longitude": 79.8612,
                "heading": 180.0,
                "speed_kph": 45.0,
                "scenario": "sunny",
                "image_base64": None
            }
        }


class ManualTSRInput(BaseModel):
    """Manual TSR input for testing without camera."""
    class_id: int = Field(..., ge=0, le=121)
    class_name: str
    confidence: float = Field(..., ge=0, le=1)


class ManualFusionRequest(BaseModel):
    """
    Manual fusion request for testing/evaluation.
    Allows setting DZ and TSR inputs directly without calling modules.
    """
    # DZ fields
    dz_risk_score: float = Field(..., ge=0, le=100)
    dz_risk_level: FusionRiskLevel = FusionRiskLevel.LOW
    dz_confidence: float = Field(default=0.85, ge=0, le=1)
    
    # TSR fields (optional)
    tsr_input: Optional[ManualTSRInput] = None
    
    # Hotspot fields (optional)
    hotspot_boost: float = Field(default=0.0, ge=0, le=1)
    hotspot_reports: int = Field(default=0, ge=0)
    
    # Context
    weather_condition: str = Field(default="Fine")
    road_surface: str = Field(default="Dry")
    speed_kph: float = Field(default=40.0, ge=0, le=200)
    
    class Config:
        json_schema_extra = {
            "example": {
                "dz_risk_score": 45.2,
                "dz_risk_level": "MEDIUM",
                "dz_confidence": 0.85,
                "tsr_input": {
                    "class_id": 88,
                    "class_name": "curve_to_left",
                    "confidence": 0.92
                },
                "weather_condition": "Rain",
                "road_surface": "Wet",
                "speed_kph": 55.0
            }
        }


# ─── Response Models ─────────────────────────────────────────────────────

class FusionReasonResponse(BaseModel):
    """A reason contributing to the fused risk assessment."""
    source: str
    description: Optional[str] = ""
    impact: str = ""


class ActiveSignResponse(BaseModel):
    """An active sign in the temporal buffer."""
    class_name: str
    confidence: float
    risk_modifier: float
    age_seconds: float


class DZContributionResponse(BaseModel):
    """DZ module's contribution to the fused result."""
    risk_score: float
    risk_level: str
    confidence: float
    mass_function: Optional[Dict] = None


class TSRContributionResponse(BaseModel):
    """TSR module's contribution to the fused result."""
    detected: bool
    class_name: Optional[str] = None
    confidence: Optional[float] = None
    risk_category: Optional[str] = None
    base_modifier: Optional[float] = None
    effective_modifier: Optional[float] = None
    aggregate: Optional[Dict] = None


class FusedPredictionResponse(BaseModel):
    """Complete fused risk prediction response."""
    # Core fused assessment
    fused_risk_score: float = Field(..., ge=0, le=100)
    fused_risk_level: FusionRiskLevel
    
    # Dempster-Shafer quantities
    belief_dangerous: float = Field(..., ge=0, le=1)
    plausibility_dangerous: float = Field(..., ge=0, le=1)
    pignistic_probability: float = Field(..., ge=0, le=1)
    conflict_measure: float = Field(..., ge=0, le=1)
    uncertainty_width: float = Field(..., ge=0, le=1)
    fused_confidence: float = Field(..., ge=0, le=1)
    
    # Per-module contributions
    dz_contribution: Dict
    tsr_contribution: Dict
    hotspot_contribution: Dict
    
    # Situational Reliability (SRD Novelty)
    tsr_reliability: float = Field(default=1.0, ge=0.1, le=1.0)
    tsr_discount_reasons: List[str] = []
    
    # Neuro-Symbolic Validation (NSLV Novelty)
    validation_status: str = "PLAUSIBLE"
    validation_reason: str = ""
    
    # Explainability
    fusion_reasons: List[FusionReasonResponse]
    active_signs: List[ActiveSignResponse]
    
    # Adaptive weighting transparency
    adaptive_weights: Dict = {}
    
    # Metadata
    timestamp: str
    fusion_method: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "fused_risk_score": 58.7,
                "fused_risk_level": "MEDIUM",
                "belief_dangerous": 0.52,
                "plausibility_dangerous": 0.71,
                "pignistic_probability": 0.587,
                "conflict_measure": 0.08,
                "uncertainty_width": 0.19,
                "fused_confidence": 0.87,
                "dz_contribution": {"risk_score": 45.2, "risk_level": "MEDIUM", "confidence": 0.85},
                "tsr_contribution": {"detected": True, "class_name": "curve_to_left", "confidence": 0.92},
                "hotspot_contribution": {"active": False},
                "fusion_reasons": [
                    {"source": "tsr", "description": "Detected 'curve_to_left' (confidence: 92%)", "impact": "increases_risk"},
                    {"source": "dz", "description": "Junction type increases risk", "impact": "increases_risk"}
                ],
                "active_signs": [
                    {"class_name": "curve_to_left", "confidence": 0.92, "risk_modifier": 0.40, "age_seconds": 2.1}
                ],
                "timestamp": "2026-02-16T01:00:00",
                "fusion_method": "dempster_shafer"
            }
        }


class ConflictLogEntry(BaseModel):
    """An entry in the DS conflict log."""
    timestamp: str
    conflict: float
    sources: List[Dict]


class ConflictLogResponse(BaseModel):
    """Response for conflict log endpoint."""
    count: int
    entries: List[ConflictLogEntry]


class FusionHealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    ontology_classes: int
    buffer_size: int
    conflict_log_size: int
    fusion_method: str


class OntologyProfileResponse(BaseModel):
    """Sign risk profile from the ontology."""
    class_id: int
    class_name: str
    risk_category: str
    base_risk_modifier: float
    relevance_duration_s: float
    num_contextual_rules: int


class OntologyResponse(BaseModel):
    """Full ontology listing."""
    total_classes: int
    profiles: List[OntologyProfileResponse]


class SegmentInsightResponse(BaseModel):
    """A road segment's accumulated learning insights."""
    segment: str
    lat: float
    lon: float
    avg_risk: float
    max_risk: float
    conflict_rate: float
    prediction_count: int
    needs_calibration: bool
    last_seen: str


class SegmentInsightsResponse(BaseModel):
    """Response for segment insights endpoint."""
    count: int
    segments: List[SegmentInsightResponse]


# ─── Mobile App Schemas (Flutter / Dart) ─────────────────────────────────

class MobileAnalyzeRequest(BaseModel):
    """
    Request from the Flutter app (sent every 1-2 seconds).
    This is the primary ingestion endpoint for the mobile ecosystem.
    """
    user_id: str = Field(..., description="Authenticated user ID")
    vehicle_id: str = Field(..., description="Currently active vehicle ID")
    trip_id: Optional[str] = Field(default=None, description="Active trip ID (if already started)")
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    heading: float = Field(default=0.0, ge=0, le=360)
    speed_kph: float = Field(default=0.0, ge=0, le=250)
    image_base64: Optional[str] = Field(default=None, description="Camera frame (JPEG base64)")


class MobileAnalyzeResponse(BaseModel):
    """
    Simplified response for the Flutter app.
    Contains the risk score, the LED command, and detected signs.
    """
    trip_id: str
    risk_score: float = Field(..., ge=0, le=100)
    risk_level: str  # LOW, MEDIUM, HIGH
    alert_level: str  # GREEN, YELLOW, RED — sent directly to ESP32 via BLE
    detected_signs: List[str] = []
    belief_dangerous: float = 0.0
    fused_confidence: float = 0.0
    is_degraded: bool = False  # True if TSR or DZ module was unavailable
    fusion_reasons: List[str] = []  # Human-readable reasons


# ─── User / Vehicle / Trip CRUD Schemas ──────────────────────────────────

class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=5, max_length=255)

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    created_at: str
    vehicle_count: int = 0

    class Config:
        from_attributes = True


class VehicleCreate(BaseModel):
    make_model: str = Field(..., min_length=1, max_length=255)
    vehicle_type: str = Field(default="Car")
    led_stick_mac: Optional[str] = Field(default=None, max_length=17)

class VehicleResponse(BaseModel):
    id: str
    user_id: str
    make_model: str
    vehicle_type: str
    led_stick_mac: Optional[str]
    created_at: str
    trip_count: int = 0

    class Config:
        from_attributes = True


class TripResponse(BaseModel):
    id: str
    vehicle_id: str
    start_time: str
    end_time: Optional[str]
    is_active: bool
    avg_risk_score: float
    max_risk_score: float
    total_distance_km: float
    red_alert_count: int
    yellow_alert_count: int
    point_count: int

    class Config:
        from_attributes = True


class TripListResponse(BaseModel):
    count: int
    trips: List[TripResponse]


# ─── Blackspot Report ────────────────────────────────────────────────────

class BlackspotCreate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    description: Optional[str] = None
    report_type: str = Field(default="hazard")

class BlackspotResponse(BaseModel):
    id: int
    user_id: str
    latitude: float
    longitude: float
    description: Optional[str]
    report_type: str
    created_at: str

    class Config:
        from_attributes = True


# ─── Insurance Claim ─────────────────────────────────────────────────────

class InsuranceClaimCreate(BaseModel):
    vehicle_id: str
    trip_id: Optional[str] = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    statement: Optional[str] = None
    photo_urls: Optional[List[str]] = None

class InsuranceClaimResponse(BaseModel):
    id: str
    user_id: str
    vehicle_id: str
    trip_id: Optional[str]
    latitude: float
    longitude: float
    pre_crash_speed_kph: Optional[float]
    pre_crash_risk_score: Optional[float]
    weather_condition: Optional[str]
    statement: Optional[str]
    photo_urls: Optional[List[str]]
    status: str
    created_at: str

    class Config:
        from_attributes = True


# ─── Hotspots (Permanent Danger Zones from DZ API) ──────────────────────

class HotspotItem(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    report_count: int = 0
    risk_boost: float = 0.0
    created_at: Optional[str] = None

class HotspotsListResponse(BaseModel):
    count: int
    hotspots: List[HotspotItem]


# ─── Accident Reports (Police Reporting) ─────────────────────────────────

class AccidentReportCreate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    severity: str = Field(default="MINOR")       # MINOR, MODERATE, SEVERE, FATAL
    description: Optional[str] = None
    vehicles_involved: int = Field(default=1, ge=1)
    injuries: int = Field(default=0, ge=0)
    police_notified: bool = False

class AccidentReportResponse(BaseModel):
    id: int
    user_id: str
    latitude: float
    longitude: float
    severity: str
    description: Optional[str]
    vehicles_involved: int
    injuries: int
    police_notified: bool
    status: str
    created_at: str

    class Config:
        from_attributes = True
