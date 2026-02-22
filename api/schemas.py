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
    description: str
    impact: str


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
