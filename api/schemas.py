"""
Pydantic schemas for Fusion Layer API request/response validation.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class FusionRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class YOLODetection(BaseModel):
    """A dynamic hazard detection from the mobile app's edge YOLO model."""
    hazard_class: str
    confidence: float = Field(..., ge=0, le=1)


# ─── Request Models ───────────────────────────────────────────────────────

class FusedPredictionRequest(BaseModel):
    """Request for fused risk prediction (GPS + optional camera frame)."""
    latitude: float = Field(..., ge=-90, le=90, description="GPS latitude")
    longitude: float = Field(..., ge=-180, le=180, description="GPS longitude")
    heading: float = Field(default=0.0, ge=0, le=360, description="Vehicle heading (degrees)")
    speed_kph: float = Field(default=40.0, ge=0, le=200, description="Vehicle speed (km/h)")
    scenario: str = Field(default="sunny", description="Weather scenario override")
    image_base64: Optional[str] = Field(default=None, description="Camera frame as base64 JPEG/PNG")
    is_cropped: bool = Field(default=False, description="True if the image is already cropped to the sign")
    yolo_detections: Optional[List[YOLODetection]] = Field(default=None, description="Dynamic hazards detected on edge")
    
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
    aggregate: Optional[Dict[str, Any]] = None
    bbox: Optional[List[int]] = None


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
    yolo_contribution: Dict
    
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
    is_cropped: bool = Field(default=False, description="True if the image is already cropped to the sign")
    yolo_detections: Optional[List[YOLODetection]] = Field(default=None, description="Edge detected hazards")


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

class UserCreateWithPassword(UserCreate):
    password: str = Field(..., min_length=6)

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    profile_picture_url: Optional[str] = None
    created_at: str
    vehicle_count: int = 0

class EmailCheckRequest(BaseModel):
    email: str

class EmailCheckResponse(BaseModel):
    exists: bool

class LoginRequest(BaseModel):
    email: str
    password: str

    class Config:
        from_attributes = True


class VehicleCreate(BaseModel):
    make_model: str = Field(..., min_length=1, max_length=255)
    vehicle_type: str = Field(default="Car")
    registration_number: Optional[str] = Field(default=None, max_length=50)
    led_stick_mac: Optional[str] = Field(default=None, max_length=17)

class VehicleResponse(BaseModel):
    id: str
    user_id: str
    make_model: str
    vehicle_type: str
    registration_number: Optional[str]
    led_stick_mac: Optional[str]
    created_at: str
    trip_count: int = 0

    class Config:
        from_attributes = True


class VehicleUpdateRequest(BaseModel):
    make_model: Optional[str] = None
    vehicle_type: Optional[str] = None
    registration_number: Optional[str] = None
    led_stick_mac: Optional[str] = None


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
    hard_brake_count: int = 0
    harsh_corner_count: int = 0
    safety_score: float = 100.0

    class Config:
        from_attributes = True


class TripListResponse(BaseModel):
    count: int
    trips: List[TripResponse]


class TelemetryPointResponse(BaseModel):
    """A single telemetry point in a trip replay."""
    latitude: float
    longitude: float
    speed_kph: float
    heading: float
    risk_score: float
    risk_level: str
    alert_level: str
    detected_signs: Optional[List[str]] = []
    timestamp: str

    class Config:
        from_attributes = True


class TripDetailResponse(BaseModel):
    """Full trip detail with all telemetry points for replay."""
    trip: TripResponse
    points: List[TelemetryPointResponse]
    total_points: int


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
    # Client-side pre-crash snapshot (optional — server fills from telemetry if absent)
    pre_crash_speed_kph: Optional[float] = None
    pre_crash_risk_score: Optional[float] = None

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


# ─── Social: Driver Profile ──────────────────────────────────────────────

class DriverProfileResponse(BaseModel):
    id: str
    name: str
    email: str
    avatar_color: str = "#00E676"
    bio: str = ""
    safety_score: float = 100.0
    total_trips: int = 0
    total_distance_km: float = 0.0
    xp_points: int = 0
    driver_level: int = 1
    followers_count: int = 0
    following_count: int = 0
    is_following: bool = False    # Whether the requesting user follows this user
    created_at: str = ""

class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    avatar_color: Optional[str] = None


# ─── Social: Follow System ───────────────────────────────────────────────

class FollowRequest(BaseModel):
    follower_id: str
    following_id: str

class FollowResponse(BaseModel):
    id: int
    follower_id: str
    following_id: str
    created_at: str

class FollowerListResponse(BaseModel):
    count: int
    users: List[DriverProfileResponse]


# ─── Social: Trip Sharing ────────────────────────────────────────────────

class ShareTripRequest(BaseModel):
    user_id: str
    trip_id: str
    caption: Optional[str] = None

class SharedTripResponse(BaseModel):
    id: int
    user_id: str
    user_name: str = ""
    avatar_color: str = "#00E676"
    driver_level: int = 1
    trip_id: str
    caption: Optional[str] = None
    safety_score: int = 0
    distance_km: float = 0.0
    duration_seconds: int = 0
    route_polyline: Optional[List[Dict]] = None
    like_count: int = 0
    good_drive_count: int = 0
    warning_count: int = 0
    user_reaction: Optional[str] = None   # Current user's reaction if any
    created_at: str = ""

class SharedTripFeedResponse(BaseModel):
    count: int
    trips: List[SharedTripResponse]


# ─── Social: Reactions ───────────────────────────────────────────────────

class ReactionRequest(BaseModel):
    user_id: str
    shared_trip_id: int
    reaction_type: str = Field(..., description="like, good_drive, or warning")

class ReactionResponse(BaseModel):
    id: int
    user_id: str
    shared_trip_id: int
    reaction_type: str
    created_at: str


# ─── Social: Leaderboard ────────────────────────────────────────────────

class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    name: str
    avatar_color: str = "#00E676"
    safety_score: float = 100.0
    total_trips: int = 0
    driver_level: int = 1
    xp_points: int = 0

class LeaderboardResponse(BaseModel):
    period: str
    count: int
    entries: List[LeaderboardEntry]
    user_rank: Optional[int] = None


# ─── Social: Community Posts ─────────────────────────────────────────────

class CommunityPostCreate(BaseModel):
    user_id: str
    post_type: str = "general"
    content: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    extra_data: Optional[Dict] = None

class CommunityPostResponse(BaseModel):
    id: int
    user_id: str
    user_name: str = ""
    avatar_color: str = "#00E676"
    driver_level: int = 1
    post_type: str
    content: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    extra_data: Optional[Dict] = None
    like_count: int = 0
    created_at: str = ""

class CommunityFeedResponse(BaseModel):
    count: int
    items: List[Dict]   # Mixed: shared trips + community posts


# ─── Social: Driving Challenges ──────────────────────────────────────────

class ChallengeResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    icon: str = "🛡️"
    challenge_type: str
    target_value: int
    xp_reward: int
    period: str
    is_active: bool = True

class ChallengeProgressResponse(BaseModel):
    challenge: ChallengeResponse
    current_value: int = 0
    completed: bool = False
    completed_at: Optional[str] = None
    joined_at: str = ""
    progress_pct: float = 0.0

class ChallengesListResponse(BaseModel):
    available: List[ChallengeResponse]
    active: List[ChallengeProgressResponse]
    completed: List[ChallengeProgressResponse]


# ─── Social: Shared Routes ──────────────────────────────────────────────

class SharedRouteCreate(BaseModel):
    user_id: str
    title: str
    description: Optional[str] = None
    trip_id: str   # Source trip for extracting the route polyline

class SharedRouteResponse(BaseModel):
    id: int
    user_id: str
    user_name: str = ""
    avatar_color: str = "#00E676"
    title: str
    description: Optional[str] = None
    start_lat: float = 0.0
    start_lon: float = 0.0
    end_lat: float = 0.0
    end_lon: float = 0.0
    route_polyline: Optional[List[Dict]] = None
    safety_score: int = 0
    distance_km: float = 0.0
    follower_count: int = 0
    created_at: str = ""

class SharedRoutesListResponse(BaseModel):
    count: int
    routes: List[SharedRouteResponse]


# ─── Social: Nearby Drivers ─────────────────────────────────────────────

class NearbyDriverResponse(BaseModel):
    user_id: str
    name: str
    avatar_color: str = "#00E676"
    driver_level: int = 1
    safety_score: float = 100.0
    last_active: str = ""
    distance_km: float = 0.0


# ─── Social: Notifications ───────────────────────────────────────────────

class NotificationResponse(BaseModel):
    id: int
    user_id: str
    type: str
    title: str
    message: Optional[str] = None
    extra_data: Optional[Dict] = None
    is_read: bool = False
    created_at: str

class NotificationListResponse(BaseModel):
    unread_count: int
    notifications: List[NotificationResponse]


# ─── Social: Heatmap ───────────────────────────────────────────────────

class HeatmapPoint(BaseModel):
    trip_id: str
    latitude: float
    longitude: float
    risk_score: float
    alert_level: str

class HeatmapResponse(BaseModel):
    user_id: str
    points: List[HeatmapPoint]


# ─── Social: Trip Comparison ───────────────────────────────────────────

class TripCompStats(BaseModel):
    distance_km: float
    avg_risk_score: float
    red_alerts: int
    yellow_alerts: int
    safety_score: int

class TripComparisonResponse(BaseModel):
    trip1: TripCompStats
    trip2: TripCompStats
    deltas: Dict[str, float]  # Percentage improvements or raw differences


# ─── Social: Driving Report ────────────────────────────────────────────

class DrivingReportResponse(BaseModel):
    user_id: str
    period: str
    total_distance: float
    avg_safety_score: float
    improvement_pct: float
    report_url: Optional[str] = None


# ─── Emergency Profile (WheelSafar-Inspired) ────────────────────────────

class EmergencyProfileCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    blood_type: Optional[str] = Field(default=None, description="A+, A-, B+, B-, AB+, AB-, O+, O-")
    allergies: Optional[str] = None
    medical_conditions: Optional[str] = None
    medications: Optional[str] = None
    emergency_contact_1_name: Optional[str] = None
    emergency_contact_1_phone: Optional[str] = None
    emergency_contact_2_name: Optional[str] = None
    emergency_contact_2_phone: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_policy_no: Optional[str] = None
    is_public: bool = True

class EmergencyProfileResponse(BaseModel):
    id: int
    user_id: str
    full_name: str
    blood_type: Optional[str] = None
    allergies: Optional[str] = None
    medical_conditions: Optional[str] = None
    medications: Optional[str] = None
    emergency_contact_1_name: Optional[str] = None
    emergency_contact_1_phone: Optional[str] = None
    emergency_contact_2_name: Optional[str] = None
    emergency_contact_2_phone: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_policy_no: Optional[str] = None
    is_public: bool = True
    created_at: str = ""
    updated_at: str = ""

    class Config:
        from_attributes = True


# ─── Live Trip Sharing (WheelSafar-Inspired) ────────────────────────────

class LiveTripStartRequest(BaseModel):
    user_id: str
    trip_id: str

class LiveTripUpdateRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    speed_kph: float = Field(default=0.0, ge=0)
    risk_level: str = "LOW"
    alert_level: str = "GREEN"

class LiveTripResponse(BaseModel):
    id: int
    user_id: str
    user_name: str = ""
    trip_id: str
    share_code: str
    is_active: bool = True
    latitude: float = 0.0
    longitude: float = 0.0
    speed_kph: float = 0.0
    risk_level: str = "LOW"
    alert_level: str = "GREEN"
    watcher_count: int = 0
    last_updated: str = ""
    created_at: str = ""

    class Config:
        from_attributes = True


# ─── Quick Hazard Alerts (WheelSafar-Inspired) ──────────────────────────

class QuickAlertCreate(BaseModel):
    user_id: str
    alert_type: str = Field(..., description="breakdown, tricky_road, accident_ahead, road_hazard, police_checkpoint")
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    speed_at_report: float = Field(default=0.0, ge=0)

class QuickAlertResponse(BaseModel):
    id: int
    user_id: str
    user_name: str = ""
    alert_type: str
    latitude: float
    longitude: float
    speed_at_report: float = 0.0
    is_active: bool = True
    upvote_count: int = 0
    distance_km: float = 0.0
    created_at: str = ""
    expires_at: Optional[str] = None

    class Config:
        from_attributes = True

class QuickAlertsNearbyResponse(BaseModel):
    count: int
    alerts: List[QuickAlertResponse]

# ─── Ride Groups (WheelSafar-Inspired) ──────────────────────────────────

class RideGroupCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None

class RideGroupJoin(BaseModel):
    invite_code: str = Field(..., max_length=6, min_length=6)

class GroupMemberResponse(BaseModel):
    id: int
    group_id: int
    user_id: str
    user_name: str = ""
    role: str
    status: str
    joined_at: str

    class Config:
        from_attributes = True

class RideGroupResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    invite_code: str
    created_at: str
    members: List[GroupMemberResponse] = []

    class Config:
        from_attributes = True

class GroupLiveLocationResponse(BaseModel):
    group_id: int
    group_name: str
    active_members: List[LiveTripResponse] = []

# ─── IMU Telematics (Harsh Driving Events) ──────────────────────────────

class TelematicsEventRequest(BaseModel):
    event_type: str = Field(..., description="E.g., 'hard_brake', 'harsh_corner'")
    timestamp: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

# ─── Emergency SOS ────────────────────────────────────────────────────────

class EmergencySOSRequest(BaseModel):
    user_id: str
    latitude: float
    longitude: float
    trip_id: Optional[str] = None
    risk_snapshot: Optional[float] = None
    speed_kph: Optional[float] = 0.0

class EmergencySOSResponse(BaseModel):
    status: str
    event_id: str
    notified_contacts: List[str]
    timestamp: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None


# ─── Digital Wallet ──────────────────────────────────────────────────────

class WalletCreate(BaseModel):
    license_no: Optional[str] = None
    vehicle_classes: Optional[str] = None
    license_dob: Optional[str] = None
    blood_grp: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    license_pdf_url: Optional[str] = None
    nic_name: Optional[str] = None
    nic_no: Optional[str] = None
    nic_gender: Optional[str] = None
    nic_pob: Optional[str] = None
    nic_pdf_url: Optional[str] = None

class WalletResponse(WalletCreate):
    user_id: str
    updated_at: str

    class Config:
        from_attributes = True


# ─── Social: User Status (Stories) ──────────────────────────────────────

class StatusItemCreate(BaseModel):
    user_id: str
    content_type: str = "text"  # 'text' or 'image'
    text_content: Optional[str] = None
    bg_color: Optional[str] = "#9C27B0"
    font_family: Optional[str] = "Outfit"
    media_url: Optional[str] = None
    share_location: bool = True
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class StatusItemResponse(BaseModel):
    id: int
    user_id: str
    content_type: str
    text_content: Optional[str] = None
    bg_color: Optional[str] = None
    font_family: Optional[str] = None
    media_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    created_at: str

    class Config:
        from_attributes = True


class UserStoriesResponse(BaseModel):
    user_id: str
    name: str
    avatar_color: str
    driver_level: int
    safety_score: float
    last_update_time: str
    items: List[StatusItemResponse]


class StatusFeedResponse(BaseModel):
    count: int
    feed: List[UserStoriesResponse]


class StatusMapItemResponse(BaseModel):
    user_id: str
    name: str
    avatar_color: str
    driver_level: int
    safety_score: float
    latitude: float
    longitude: float
    last_update_time: str
    item_count: int


class StatusMapResponse(BaseModel):
    count: int
    items: List[StatusMapItemResponse]


class StatusReplyRequest(BaseModel):
    sender_id: str
    status_item_id: int
    message: str


class ViewerProfileResponse(BaseModel):
    user_id: str
    name: str
    avatar_color: str
    driver_level: int
    safety_score: float
    viewed_at: str


class StatusViewersResponse(BaseModel):
    status_item_id: int
    viewer_count: int
    viewers: List[ViewerProfileResponse]


# ─── Ride Group Convoy Schemas ──────────────────────────────────────────

class ConvoyStartRequest(BaseModel):
    destination_lat: float = Field(..., ge=-90, le=90)
    destination_lon: float = Field(..., ge=-180, le=180)
    destination_name: str

class AnnouncementCreateRequest(BaseModel):
    sender_id: str
    message: str
    announcement_type: str = "text"

class GroupAnnouncementResponse(BaseModel):
    id: int
    group_id: int
    sender_id: str
    sender_name: str
    message: str
    announcement_type: str
    created_at: str

    class Config:
        from_attributes = True

class ConvoyMemberDetails(BaseModel):
    user_id: str
    user_name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed_kph: Optional[float] = None
    risk_level: Optional[str] = None
    alert_level: Optional[str] = None
    last_updated: Optional[str] = None
    distance_remaining_km: Optional[float] = None
    is_active: bool = False
    is_lead: bool = False
    is_off_route: bool = False

class ConvoyLiveDetailsResponse(BaseModel):
    group_id: int
    group_name: Optional[str] = None
    convoy_active: bool
    destination_lat: Optional[float] = None
    destination_lon: Optional[float] = None
    destination_name: Optional[str] = None
    active_members: List[ConvoyMemberDetails]
    announcements: List[GroupAnnouncementResponse]
    active_polls: List[ConvoyPollResponse] = []


class ConvoyPollCreateRequest(BaseModel):
    poll_type: str = Field(default="rest")  # 'fuel', 'rest', 'custom'
    option_name: str
    latitude: float
    longitude: float
    creator_id: str


class ConvoyPollVoteRequest(BaseModel):
    user_id: str
    vote: str  # 'yes', 'no'


class ConvoyPollResponse(BaseModel):
    id: int
    group_id: int
    creator_id: str
    creator_name: str
    poll_type: str
    option_name: str
    latitude: float
    longitude: float
    status: str  # 'active', 'accepted', 'rejected'
    yes_votes: List[str] = []
    no_votes: List[str] = []
    created_at: str
    expires_at: str

    class Config:
        from_attributes = True


