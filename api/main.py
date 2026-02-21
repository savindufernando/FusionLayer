"""
Fusion Layer — Unified API Gateway
FastAPI service that orchestrates TSR + DZ modules for fused risk prediction.

Endpoints:
  POST /api/fused-predict        — Manual fusion with pre-computed inputs
  POST /api/fused-predict/auto   — Automatic fusion calling TSR + DZ APIs
  GET  /api/fusion/health        — Health check
  GET  /api/fusion/conflict-log  — DS conflict log for research analysis
  GET  /api/fusion/ontology      — List sign-risk ontology profiles
  POST /api/fusion/reset         — Reset engine state (new trip)
"""

import os
import yaml
import time
import logging
import httpx
import base64
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from .schemas import (
    FusedPredictionRequest,
    ManualFusionRequest,
    FusedPredictionResponse,
    FusionReasonResponse,
    ActiveSignResponse,
    ConflictLogResponse,
    ConflictLogEntry,
    FusionHealthResponse,
    OntologyResponse,
    OntologyProfileResponse
)

from src.fusion_engine import FusionEngine, TSRInput, DZInput, HotspotInput


# ─── Globals ──────────────────────────────────────────────────────────────
engine: Optional[FusionEngine] = None
config: dict = {}

logger = logging.getLogger("fusion_api")


def load_config() -> dict:
    """Load configuration from config.yaml."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f)
        
        # Flatten nested config into what FusionEngine expects
        fusion_cfg = raw.get("fusion", {})
        buffer_cfg = raw.get("buffer", {})
        
        return {
            "fusion_method": fusion_cfg.get("method", "dempster_shafer"),
            "tsr_weight": fusion_cfg.get("tsr_weight", 0.35),
            "dz_weight": fusion_cfg.get("dz_weight", 0.65),
            "conflict_threshold": fusion_cfg.get("conflict_threshold", 0.3),
            "sign_decay_lambda": buffer_cfg.get("sign_decay_lambda", 0.1),
            "buffer_max_signs": buffer_cfg.get("max_signs", 20),
            "buffer_max_age_seconds": buffer_cfg.get("max_age_seconds", 60),
            "min_tsr_confidence": raw.get("min_tsr_confidence", 0.6),
            "min_dz_confidence": raw.get("min_dz_confidence", 0.3),
            "threshold_high": raw.get("threshold_high", 65.0),
            "threshold_medium": raw.get("threshold_medium", 35.0),
            "ema_alpha": raw.get("ema_alpha", 0.35),
            # Module URLs for auto-predict
            "tsr_url": raw.get("modules", {}).get("tsr", {}).get("url", "http://localhost:8001"),
            "tsr_endpoint": raw.get("modules", {}).get("tsr", {}).get("predict_endpoint", "/predict"),
            "dz_url": raw.get("modules", {}).get("dz", {}).get("url", "http://localhost:8000"),
            "dz_endpoint": raw.get("modules", {}).get("dz", {}).get("predict_endpoint", "/api/predict"),
        }
    return {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize fusion engine on startup."""
    global engine, config
    config = load_config()
    engine = FusionEngine(config)
    
    errors = engine.ontology.validate()
    if errors:
        logger.warning(f"Ontology validation: {errors}")
    else:
        logger.info(f"Ontology loaded: {engine.ontology.num_classes} sign classes")
    
    logger.info("Fusion Engine initialized")
    yield
    logger.info("Fusion Engine shutting down")


# ─── App ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Fusion Layer API",
    description=(
        "Adaptive Multi-Modal Risk Integration using Dempster-Shafer Theory. "
        "Combines Traffic Sign Recognition (TSR) and Dangerous Zone Prediction (DZ) "
        "into a unified risk assessment."
    ),
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve dashboard static files
dashboard_dir = Path(__file__).parent.parent / "dashboard"
if dashboard_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")


@app.get("/")
async def root_redirect():
    """Redirect root to dashboard."""
    return RedirectResponse(url="/dashboard/")


# ─── Endpoints ────────────────────────────────────────────────────────────

@app.post("/api/fused-predict", response_model=FusedPredictionResponse)
async def fused_predict_manual(request: ManualFusionRequest):
    """
    Manual fused risk prediction.
    
    Accepts pre-computed DZ and TSR inputs directly — useful for testing,
    evaluation, and ablation studies without running the full modules.
    """
    if engine is None:
        raise HTTPException(status_code=503, detail="Fusion engine not initialized")
    
    # Construct DZ input
    dz = DZInput(
        risk_score=request.dz_risk_score,
        risk_level=request.dz_risk_level.value,
        confidence=request.dz_confidence,
        risk_probability=request.dz_risk_score / 100.0,
        weather_condition=request.weather_condition,
        road_surface=request.road_surface,
        speed_kph=request.speed_kph
    )
    
    # Construct TSR input (optional)
    tsr = None
    if request.tsr_input:
        tsr = TSRInput(
            class_id=request.tsr_input.class_id,
            class_name=request.tsr_input.class_name,
            confidence=request.tsr_input.confidence,
            is_confident=request.tsr_input.confidence >= 0.5
        )
    
    # Construct hotspot input (optional)
    hotspot = None
    if request.hotspot_boost > 0:
        hotspot = HotspotInput(
            risk_boost=request.hotspot_boost,
            report_count=request.hotspot_reports
        )
    
    # Fuse
    result = engine.fuse(dz_input=dz, tsr_input=tsr, hotspot_input=hotspot)
    
    return _result_to_response(result)


@app.post("/api/fused-predict/auto", response_model=FusedPredictionResponse)
async def fused_predict_auto(request: FusedPredictionRequest):
    """
    Automatic fused risk prediction.
    
    Calls TSR and DZ module APIs, then fuses their outputs.
    Requires both modules to be running as services.
    """
    if engine is None:
        raise HTTPException(status_code=503, detail="Fusion engine not initialized")
    
    tsr_url = config.get("tsr_url", "http://localhost:8001")
    tsr_endpoint = config.get("tsr_endpoint", "/predict")
    dz_url = config.get("dz_url", "http://localhost:8000")
    dz_endpoint = config.get("dz_endpoint", "/api/predict")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # ─── Call DZ Module ───────────────────────────────────────
        try:
            dz_response = await client.post(
                f"{dz_url}{dz_endpoint}",
                json={
                    "latitude": request.latitude,
                    "longitude": request.longitude,
                    "heading": request.heading,
                    "speed_kph": request.speed_kph,
                    "scenario": request.scenario
                }
            )
            dz_data = dz_response.json()
            
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
        except Exception as e:
            logger.error(f"DZ module call failed: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"DZ module unavailable: {str(e)}"
            )
        
        # ─── Call TSR Module (if image provided) ──────────────────
        tsr = None
        if request.image_base64:
            try:
                tsr_response = await client.post(
                    f"{tsr_url}{tsr_endpoint}",
                    json={"image": request.image_base64}
                )
                tsr_data = tsr_response.json()
                
                tsr = TSRInput(
                    class_id=tsr_data.get("class_id", 0),
                    class_name=tsr_data.get("class_name", "unknown"),
                    confidence=tsr_data.get("confidence", 0),
                    is_confident=tsr_data.get("is_confident", False),
                    latitude=request.latitude,
                    longitude=request.longitude
                )
            except Exception as e:
                logger.warning(f"TSR module call failed (continuing DZ-only): {e}")
    
    # Fuse
    result = engine.fuse(dz_input=dz, tsr_input=tsr)
    return _result_to_response(result)


@app.get("/api/fusion/health", response_model=FusionHealthResponse)
async def health_check():
    """Health check showing fusion engine status."""
    if engine is None:
        return FusionHealthResponse(
            status="initializing",
            version="1.0.0",
            ontology_classes=0,
            buffer_size=0,
            conflict_log_size=0,
            fusion_method="unknown"
        )
    
    return FusionHealthResponse(
        status="healthy",
        version="1.0.0",
        ontology_classes=engine.ontology.num_classes,
        buffer_size=engine.buffer.size,
        conflict_log_size=len(engine.get_conflict_log()),
        fusion_method=engine.config.get("fusion_method", "dempster_shafer")
    )


@app.get("/api/fusion/conflict-log", response_model=ConflictLogResponse)
async def get_conflict_log():
    """
    Get Dempster-Shafer conflict log.
    
    Returns all logged conflict events where K > threshold.
    Useful for research analysis of inter-module disagreement.
    """
    if engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    log = engine.get_conflict_log()
    return ConflictLogResponse(
        count=len(log),
        entries=[ConflictLogEntry(**entry) for entry in log]
    )


@app.get("/api/fusion/ontology", response_model=OntologyResponse)
async def get_ontology():
    """List all sign-risk ontology profiles."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    profiles = engine.ontology.get_all_profiles()
    return OntologyResponse(
        total_classes=len(profiles),
        profiles=[
            OntologyProfileResponse(
                class_id=p.class_id,
                class_name=p.class_name,
                risk_category=p.risk_category.value,
                base_risk_modifier=p.base_risk_modifier,
                relevance_duration_s=p.relevance_duration_s,
                num_contextual_rules=len(p.contextual_rules)
            )
            for p in sorted(profiles, key=lambda x: x.class_id)
        ]
    )


@app.post("/api/fusion/reset")
async def reset_engine():
    """Reset fusion engine state (e.g., start of new trip)."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    engine.reset()
    return {"status": "reset", "message": "Buffer, EMA history, and conflict log cleared"}


# ─── Helpers ──────────────────────────────────────────────────────────────

def _result_to_response(result) -> FusedPredictionResponse:
    """Convert FusionResult to API response."""
    return FusedPredictionResponse(
        fused_risk_score=result.fused_risk_score,
        fused_risk_level=result.fused_risk_level,
        belief_dangerous=result.belief_dangerous,
        plausibility_dangerous=result.plausibility_dangerous,
        pignistic_probability=result.pignistic_probability,
        conflict_measure=result.conflict_measure,
        uncertainty_width=result.uncertainty_width,
        fused_confidence=result.fused_confidence,
        dz_contribution=result.dz_contribution,
        tsr_contribution=result.tsr_contribution,
        hotspot_contribution=result.hotspot_contribution,
        fusion_reasons=[
            FusionReasonResponse(**r) for r in result.fusion_reasons
        ],
        active_signs=[
            ActiveSignResponse(**s) for s in result.active_signs
        ],
        timestamp=result.timestamp,
        fusion_method=result.fusion_method
    )


# ─── Entry Point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
