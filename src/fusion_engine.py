"""
Fusion Engine Module
Orchestrates multi-modal risk integration using Dempster-Shafer Theory.

This is the central component of the Fusion Layer, responsible for:
1. Receiving outputs from TSR (sign detections) and DZ (zone risk predictions)
2. Converting outputs into DS mass functions via the ontology and evidence module
3. Combining evidence using Dempster's Rule of Combination
4. Producing a unified risk assessment with explainability

Architecture:
    TSR Output     → SignRiskOntology → EvidenceConstructor → ┐
    DZ Output      → ─────────────── → EvidenceConstructor → ├─→ DSCombiner → FusionResult
    Hotspot Data   → ─────────────── → EvidenceConstructor → ┘
    TemporalBuffer → Aggregate Sign Evidence ───────────────→ ┘
"""

import json
import math
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .sign_risk_ontology import SignRiskOntology, SignRiskProfile
from .evidence import (
    MassFunction, EvidenceConstructor,
    dempster_combine, combine_multiple
)
from .temporal_buffer import (
    TemporalSignBuffer, SignDetection, AggregateSignEvidence
)
from .logic_validator import LogicValidator, ValidationStatus


logger = logging.getLogger(__name__)


@dataclass
class TSRInput:
    """Input from the Traffic Sign Recognition module."""
    class_id: int
    class_name: str
    confidence: float
    is_confident: bool
    top_k: Optional[List[Dict]] = None
    timestamp: Optional[float] = None
    latitude: float = 0.0
    longitude: float = 0.0
    bbox: Optional[List[int]] = None
    epistemic_uncertainty: float = 0.0


@dataclass
class DZInput:
    """Input from the Dangerous Zone Prediction module."""
    risk_score: float        # 0-100
    risk_level: str          # "LOW", "MEDIUM", "HIGH"
    confidence: float        # 0-1
    risk_probability: float  # Raw ensemble probability (0-1)
    weather_condition: str = "Fine"
    road_surface: str = "Dry"
    is_overspeeding: bool = False
    speed_deviation_kph: float = 0.0
    speed_kph: float = 40.0
    speed_limit_kph: float = 50.0
    reasons: List[Dict] = field(default_factory=list)


@dataclass
class HotspotInput:
    """Input from crowdsourced accident reporting."""
    risk_boost: float = 0.0
    report_count: int = 0


@dataclass
class YOLOInput:
    """Input from the dynamic hazard detection module (YOLO)."""
    has_hazard: bool
    hazard_class: str
    confidence: float
    timestamp: Optional[float] = None


@dataclass
class FusionResult:
    """
    Unified risk assessment output from the fusion engine.
    
    Contains the fused Dempster-Shafer risk score along with
    per-module contributions, conflict analysis, and explainability.
    """
    # Fused risk assessment
    fused_risk_score: float          # 0-100 (final unified score)
    fused_risk_level: str            # "LOW", "MEDIUM", "HIGH"
    
    # Dempster-Shafer quantities
    belief_dangerous: float          # Bel(D) — lower bound
    plausibility_dangerous: float    # Pl(D) — upper bound
    pignistic_probability: float     # BetP(D) — point estimate
    conflict_measure: float          # K — inter-source disagreement
    
    # Uncertainty quantification
    uncertainty_width: float         # Pl(D) - Bel(D)
    fused_confidence: float          # Overall confidence in the result
    
    # Per-module contributions
    dz_contribution: Dict = field(default_factory=dict)
    tsr_contribution: Dict = field(default_factory=dict)
    hotspot_contribution: Dict = field(default_factory=dict)
    yolo_contribution: Dict = field(default_factory=dict)
    
    # Situational Reliability (SRD Novelty)
    tsr_reliability: float = 1.0
    tsr_discount_reasons: List[str] = field(default_factory=list)
    
    # Explainability
    fusion_reasons: List[Dict] = field(default_factory=list)
    active_signs: List[Dict] = field(default_factory=list)
    
    # Neuro-Symbolic Validation (NSLV Novelty)
    validation_status: str = "PLAUSIBLE"
    validation_reason: str = ""
    
    # Adaptive weighting transparency
    adaptive_weights: Dict = field(default_factory=dict)
    
    # Metadata
    timestamp: str = ""
    fusion_method: str = "dempster_shafer"
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary for JSON response."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)


class FusionEngine:
    """
    Multi-modal risk fusion engine using Dempster-Shafer Theory.
    
    Combines evidence from:
    - Traffic Sign Recognition (visual perception)
    - Dangerous Zone Prediction (structured sensor/model)
    - Crowdsourced Accident Hotspots (community reporting)
    
    Usage:
        engine = FusionEngine(config)
        result = engine.fuse(tsr_input, dz_input, hotspot_input)
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the fusion engine.
        
        Args:
            config: Configuration dict (see config.yaml)
        """
        self.config = config or self._default_config()
        
        # Core components
        self.ontology = SignRiskOntology()
        self.buffer = TemporalSignBuffer(
            decay_lambda=self.config.get("sign_decay_lambda", 0.1),
            max_signs=self.config.get("buffer_max_signs", 20),
            max_age_s=self.config.get("buffer_max_age_seconds", 60)
        )
        
        # Thresholds
        self.min_tsr_confidence = self.config.get("min_tsr_confidence", 0.20)
        self.min_dz_confidence = self.config.get("min_dz_confidence", 0.4)
        
        # NSLV Novelty
        self.validator = LogicValidator(self.config)
        
        self.conflict_threshold = self.config.get("conflict_threshold", 0.3)
        
        # Risk level thresholds (on fused 0-100 scale)
        self.threshold_high = self.config.get("threshold_high", 65.0)
        self.threshold_medium = self.config.get("threshold_medium", 35.0)
        
        # EMA smoothing for temporal stability
        self.ema_alpha = self.config.get("ema_alpha", 0.35)
        self._ema_history: List[float] = []
        
        # Conflict log for research analysis
        self._conflict_log: List[Dict] = []
        self._max_conflict_log = 1000
        
        # ─── Adaptive weighting config ────────────────────────────
        self.adaptive_weighting = self.config.get("adaptive_weighting", True)
        self.base_tsr_weight = self.config.get("tsr_weight", 0.35)
        self.base_dz_weight = self.config.get("dz_weight", 0.65)
        
        # ─── Peak hour config (Colombo traffic patterns) ─────────
        self.peak_hours = self.config.get("peak_hours", [
            (7, 0, 9, 0),       # 7:00 AM – 9:00 AM
            (16, 30, 19, 0),    # 4:30 PM – 7:00 PM
        ])
        
        # ─── Segment history for learning ─────────────────────────
        self._segment_history: Dict[str, Dict] = {}
        self._segment_grid_precision = 3  # ~100 m grid
        
        # Validate ontology on init
        errors = self.ontology.validate()
        if errors:
            logger.warning(f"Ontology validation errors: {errors}")
    
    @staticmethod
    def _default_config() -> Dict:
        """Default fusion configuration."""
        return {
            "fusion_method": "dempster_shafer",
            "tsr_weight": 0.35,
            "dz_weight": 0.65,
            "conflict_threshold": 0.3,
            "sign_decay_lambda": 0.05,
            "buffer_max_signs": 20,
            "buffer_max_age_seconds": 60,
            "min_tsr_confidence": 0.20,
            "min_dz_confidence": 0.3,
            "threshold_high": 65.0,
            "threshold_medium": 35.0,
            "ema_alpha": 0.35
        }
    
    def fuse(
        self,
        dz_input: DZInput,
        tsr_input: Optional[TSRInput] = None,
        hotspot_input: Optional[HotspotInput] = None,
        yolo_input: Optional[YOLOInput] = None,
        current_time: Optional[float] = None
    ) -> FusionResult:
        """
        Perform multi-modal risk fusion.
        
        This is the main entry point. It:
        1. Processes TSR input through ontology → temporal buffer
        2. Constructs mass functions from all sources
        3. Combines using Dempster's Rule
        4. Applies EMA smoothing
        5. Generates explainability
        
        Args:
            dz_input: Dangerous Zone module output (required)
            tsr_input: Traffic Sign Recognition output (optional)
            hotspot_input: Crowdsourced hotspot data (optional)
            current_time: Override current time for testing
            
        Returns:
            FusionResult with unified risk assessment
        """
        now = current_time or time.time()
        timestamp = datetime.fromtimestamp(now).isoformat()
        reasons = []
        # ─── Defensive Check: Ensure inputs are not None ──────────────
        if dz_input is None:
            # Create a safe neutral fallback for DZ
            dz_input = DZInput(
                risk_score=25.0, risk_level="LOW", confidence=0.0,
                risk_probability=0.25, weather_condition="Unknown",
                road_surface="Unknown", speed_kph=0
            )
            
        if tsr_input is None:
            # Create a silent fallback for TSR
            tsr_input = TSRInput(
                class_id=0, class_name="none", confidence=0.0,
                is_confident=False, latitude=0.0, longitude=0.0
            )

        tsr_reliability = 1.0
        tsr_discount_reasons = []
        v_status = "PLAUSIBLE"
        v_reason = "No active sign evidence to validate"
        
        # ─── Step 1: Process TSR input through ontology ───────────────
        tsr_mass = MassFunction(source="tsr(absent)")
        tsr_contribution = {"detected": False}
        
        # Uncertainty-Aware Fusion check
        if tsr_input and getattr(tsr_input, 'epistemic_uncertainty', 0.0) > 0.15:
            reasons.append({
                "source": "tsr_uncertainty",
                "description": f"Ignored '{tsr_input.class_name}' due to high epistemic uncertainty ({tsr_input.epistemic_uncertainty:.3f})",
                "impact": "decreases_confidence"
            })
            tsr_input = None  # Nullify to drop this uncertain evidence
        
        if tsr_input and tsr_input.is_confident and tsr_input.confidence >= self.min_tsr_confidence:
            profile = self.ontology.get_profile(tsr_input.class_id)
            
            if profile:
                # Determine environmental context from DZ input
                is_night = dz_input.weather_condition in ("Dark", "Night") or \
                           "Night" in dz_input.weather_condition
                is_wet = dz_input.road_surface in ("Wet", "Snow", "Flood", "Ice")
                is_fog = "Fog" in dz_input.weather_condition
                is_peak = self._is_peak_hour(now)
                weather_code = self._weather_str_to_code(dz_input.weather_condition)
                
                # Compute context-adjusted risk modifier
                effective_modifier = self.ontology.compute_effective_modifier(
                    profile,
                    weather_code=weather_code,
                    is_night=is_night,
                    is_fog=is_fog,
                    is_wet=is_wet,
                    is_peak_hour=is_peak,
                    speed_kph=dz_input.speed_kph,
                    speed_limit_kph=dz_input.speed_limit_kph
                )
                
                # Add to temporal buffer
                detection = SignDetection(
                    class_id=tsr_input.class_id,
                    class_name=tsr_input.class_name,
                    confidence=tsr_input.confidence,
                    timestamp=tsr_input.timestamp or now,
                    latitude=tsr_input.latitude,
                    longitude=tsr_input.longitude,
                    risk_modifier=effective_modifier,
                    relevance_duration_s=profile.relevance_duration_s
                )
                self.buffer.add(detection)
                
                tsr_contribution = {
                    "detected": True,
                    "class_name": tsr_input.class_name,
                    "confidence": round(tsr_input.confidence, 3),
                    "risk_category": profile.risk_category.value,
                    "base_modifier": round(profile.base_risk_modifier, 3),
                    "effective_modifier": round(effective_modifier, 3),
                    "bbox": tsr_input.bbox
                }
                
                if effective_modifier > 0.2:
                    reasons.append({
                        "source": "tsr",
                        "description": f"Detected '{tsr_input.class_name}' "
                                       f"(confidence: {tsr_input.confidence:.0%}, "
                                       f"risk modifier: {effective_modifier:.2f})",
                        "impact": "increases_risk"
                    })
        
        # ─── Step 2: Get aggregate sign evidence from buffer ──────────
        aggregate = self.buffer.get_aggregate_evidence(now)
        
        # ─── Adaptive weight computation ────────────────────────────
        adaptive_w = self._compute_adaptive_weights(
            dz_confidence=dz_input.confidence,
            tsr_avg_confidence=(
                aggregate.total_decay_weight / aggregate.num_active_signs
                if aggregate.num_active_signs > 0 else 0
            ),
            num_signs=aggregate.num_active_signs
        )
        
        if aggregate.num_active_signs > 0:
            # Use weighted average modifier (accounts for decay)
            agg_modifier = aggregate.weighted_avg_modifier * aggregate.compound_factor
            agg_modifier = min(agg_modifier, 1.0)
            
            # Average decay weight as confidence proxy
            avg_decay = aggregate.total_decay_weight / aggregate.num_active_signs if aggregate.num_active_signs > 0 else 0
            
            # ─── Situational Reliability Discounting (Novelty) ─────────
            tsr_reliability, tsr_discount_reasons = self._compute_tsr_reliability(dz_input)
            
            # Scale TSR evidence strength by adaptive weight ratio
            weight_scale = adaptive_w["tsr"] / self.base_tsr_weight if self.adaptive_weighting else 1.0
            scaled_confidence = min(avg_decay * weight_scale, 1.0)
            
            # ─── Neuro-Symbolic Validation (Novelty) ───────────────────
            # Validate the aggregate modifier (or primary sign if we had it)
            # For simplicity, we'll validate against the 'reason' if available
            primary_sign = aggregate.to_dict().get("primary_sign_name", "Unknown")
            v_status, v_reason = self.validator.validate_detection(
                class_name=primary_sign,
                confidence=scaled_confidence,
                speed_kph=dz_input.speed_kph,
                road_type=dz_input.road_surface  # Using surface as proxy for road context for now
            )
            
            # Adjust confidence/mass based on validation status
            v_multiplier = self.validator.get_risk_adjustment(v_status)
            scaled_confidence = min(scaled_confidence * v_multiplier, 1.0)
            
            tsr_mass = EvidenceConstructor.from_tsr(
                sign_risk_modifier=agg_modifier,
                tsr_confidence=scaled_confidence,
                temporal_decay=1.0,
                min_confidence=0.0,
                reliability_discount=tsr_reliability
            )
            
            tsr_contribution["validation"] = {
                "status": v_status,
                "reason": v_reason,
                "multiplier": v_multiplier
            }

            if v_status in (ValidationStatus.CONTRADICTION, ValidationStatus.QUESTIONABLE):
                reasons.append({
                    "source": "fusion_nslv",
                    "description": f"Symbolic logic flagged detection as {v_status}: {v_reason}",
                    "impact": "decreases_confidence"
                })
            elif v_status == ValidationStatus.RULE_OVERRIDE:
                 reasons.append({
                    "source": "fusion_nslv",
                    "description": f"RULE OVERRIDE: {v_reason}",
                    "impact": "increases_risk"
                })
            
            tsr_contribution["aggregate"] = aggregate.to_dict()
            tsr_contribution["reliability"] = tsr_reliability
            tsr_contribution["reliability_reasons"] = tsr_discount_reasons

            if tsr_reliability < 1.0:
                reasons.append({
                    "source": "fusion_srd",
                    "description": f"Camera reliability discounted to {tsr_reliability*100:.0f}% due to environment",
                    "impact": "uncertainty"
                })
            
            if aggregate.num_active_signs > 1:
                reasons.append({
                    "source": "tsr_buffer",
                    "description": f"{aggregate.num_active_signs} active signs in context "
                                   f"(compound factor: {aggregate.compound_factor:.2f})",
                    "impact": "contextual"
                })
        
        # ─── Step 3: Construct DZ mass function ───────────────────────
        dz_probability = dz_input.risk_score / 100.0  # Convert 0-100 to 0-1
        
        dz_mass = EvidenceConstructor.from_dz(
            risk_probability=dz_probability,
            dz_confidence=dz_input.confidence,
            min_confidence=self.min_dz_confidence
        )
        
        dz_contribution = {
            "risk_score": dz_input.risk_score,
            "risk_level": dz_input.risk_level,
            "confidence": dz_input.confidence,
            "mass_function": dz_mass.to_dict()
        }
        
        if dz_input.risk_level in ("MEDIUM", "HIGH"):
            for r in dz_input.reasons:
                desc = r.get("description", r.get("feature", "Unknown factor"))
                reasons.append({
                    "source": "dz",
                    "description": desc,
                    "impact": "increases_risk"
                })
        
        # ─── Step 4: Construct hotspot mass function ──────────────────
        hotspot_mass = MassFunction(source="hotspot(none)")
        hotspot_contribution = {"active": False}
        
        if hotspot_input and hotspot_input.risk_boost > 0:
            hotspot_mass = EvidenceConstructor.from_hotspot(
                risk_boost=hotspot_input.risk_boost,
                report_count=hotspot_input.report_count
            )
            hotspot_contribution = {
                "active": True,
                "risk_boost": hotspot_input.risk_boost,
                "report_count": hotspot_input.report_count,
                "mass_function": hotspot_mass.to_dict()
            }
            reasons.append({
                "source": "hotspot",
                "description": f"Accident hotspot ({hotspot_input.report_count} reports)",
                "impact": "increases_risk"
            })
        
        # ─── Step 4.5: Construct YOLO mass function ───────────────────────
        yolo_mass = MassFunction(source="yolo(none)")
        yolo_contribution = {"detected": False}
        
        if yolo_input and yolo_input.has_hazard:
            yolo_mass = EvidenceConstructor.from_yolo(
                hazard_class=yolo_input.hazard_class,
                yolo_confidence=yolo_input.confidence
            )
            yolo_contribution = {
                "detected": True,
                "hazard_class": yolo_input.hazard_class,
                "confidence": yolo_input.confidence,
                "mass_function": yolo_mass.to_dict()
            }
            reasons.append({
                "source": "yolo",
                "description": f"Dynamic Hazard Detected: '{yolo_input.hazard_class}' (confidence: {yolo_input.confidence:.0%})",
                "impact": "critical_risk"
            })
            
        # ─── Step 5: Combine evidence via Dempster's Rule ─────────────
        mass_functions = [dz_mass]
        if tsr_mass.m_uncertain < 0.999:  # TSR has actual evidence
            mass_functions.append(tsr_mass)
        if hotspot_mass.m_uncertain < 0.999:  # Hotspot has evidence
            mass_functions.append(hotspot_mass)
        if yolo_mass.m_uncertain < 0.999:  # YOLO has evidence
            mass_functions.append(yolo_mass)
        
        fused_mass, conflicts = combine_multiple(mass_functions)
        
        # Total conflict
        total_conflict = max(conflicts) if conflicts else 0.0
        
        # Log conflict for research analysis
        if total_conflict > self.conflict_threshold:
            self._log_conflict(total_conflict, mass_functions, timestamp)
            reasons.append({
                "source": "fusion",
                "description": f"Evidence conflict detected (K={total_conflict:.3f}): "
                               f"TSR and DZ modules disagree",
                "impact": "uncertainty"
            })
        
        # ─── Step 6: Compute final risk score ─────────────────────────
        # Use pignistic probability as the point estimate
        raw_score = fused_mass.pignistic_probability * 100.0
        
        # Apply EMA smoothing
        smoothed_score = self._apply_ema(raw_score)
        
        # Determine risk level
        risk_level = self._get_risk_level(smoothed_score)
        
        # Compute fused confidence
        fused_confidence = self._compute_fused_confidence(
            dz_input.confidence,
            tsr_mass,
            total_conflict,
            aggregate.num_active_signs
        )
        
        # Reliability already computed earlier in Step 2 if signs present
        if aggregate.num_active_signs == 0:
            tsr_reliability, tsr_discount_reasons = self._compute_tsr_reliability(dz_input)
        
        # ─── Step 7: Update segment history ─────────────────────────────
        self._update_segment_history(
            dz_input.speed_kph,
            getattr(tsr_input, 'latitude', 0) or 0,
            getattr(tsr_input, 'longitude', 0) or 0,
            smoothed_score, total_conflict, timestamp
        )
        
        # ─── Step 8: Build result ─────────────────────────────────────
        return FusionResult(
            fused_risk_score=round(smoothed_score, 1),
            fused_risk_level=risk_level,
            belief_dangerous=round(fused_mass.belief_dangerous, 4),
            plausibility_dangerous=round(fused_mass.plausibility_dangerous, 4),
            pignistic_probability=round(fused_mass.pignistic_probability, 4),
            conflict_measure=round(total_conflict, 4),
            uncertainty_width=round(fused_mass.uncertainty_width, 4),
            fused_confidence=round(fused_confidence, 3),
            dz_contribution=dz_contribution,
            tsr_contribution=tsr_contribution,
            hotspot_contribution=hotspot_contribution,
            yolo_contribution=yolo_contribution,
            tsr_reliability=round(tsr_reliability, 3),
            tsr_discount_reasons=tsr_discount_reasons,
            validation_status=v_status,
            validation_reason=v_reason,
            fusion_reasons=reasons,
            active_signs=[{
                "class_name": d.class_name,
                "confidence": round(d.confidence, 3),
                "risk_modifier": round(d.risk_modifier, 3),
                "age_seconds": round(now - d.timestamp, 1)
            } for d in self.buffer.get_active_detections(now)],
            adaptive_weights=adaptive_w,
            timestamp=timestamp,
            fusion_method=self.config.get("fusion_method", "dempster_shafer")
        )
    
    def _apply_ema(self, score: float) -> float:
        """Apply exponential moving average smoothing."""
        if not self._ema_history:
            self._ema_history.append(score)
            return score
        
        prev = self._ema_history[-1]
        smoothed = self.ema_alpha * score + (1 - self.ema_alpha) * prev
        self._ema_history.append(smoothed)
        
        # Keep recent history only
        if len(self._ema_history) > 120:
            self._ema_history = self._ema_history[-120:]
        
        return smoothed
    
    def _get_risk_level(self, score: float) -> str:
        """Determine risk level from fused score."""
        if score >= self.threshold_high:
            return "HIGH"
        elif score >= self.threshold_medium:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _compute_fused_confidence(
        self,
        dz_confidence: float,
        tsr_mass: MassFunction,
        conflict: float,
        num_signs: int
    ) -> float:
        """
        Compute overall confidence in the fused result.
        
        Factors:
        - DZ module confidence (primary contributor)
        - TSR evidence strength (more signs = more context)
        - Inter-source conflict (high conflict = low confidence)
        """
        confidence = dz_confidence
        
        # TSR evidence boost (more signs in context = higher confidence)
        if num_signs > 0:
            tsr_boost = min(num_signs * 0.03, 0.15)
            # But only if TSR evidence is strong
            if tsr_mass.m_uncertain < 0.8:
                confidence += tsr_boost
        
        # Conflict penalty
        confidence -= conflict * 0.3
        
        # Uncertainty penalty from fused mass
        confidence -= tsr_mass.uncertainty_width * 0.1
        
        return max(0.1, min(1.0, confidence))
    
    def _log_conflict(self, conflict: float, masses: List[MassFunction], timestamp: str):
        """Log significant conflicts for research analysis."""
        entry = {
            "timestamp": timestamp,
            "conflict": conflict,
            "sources": [m.to_dict() for m in masses]
        }
        self._conflict_log.append(entry)
        if len(self._conflict_log) > self._max_conflict_log:
            self._conflict_log = self._conflict_log[-self._max_conflict_log:]
        
        logger.info(f"DS Conflict K={conflict:.3f} between {[m.source for m in masses]}")
    
    def get_conflict_log(self) -> List[Dict]:
        """Get recent conflict events for research analysis."""
        return list(self._conflict_log)
    
    def reset(self):
        """Reset engine state for a new trip/session."""
        self.buffer.clear()
        self._ema_history.clear()
        self._conflict_log.clear()
        # Note: segment history is NOT cleared — it persists across trips
    
    # ─── Adaptive Weighting ────────────────────────────────────────────
    
    def _compute_tsr_reliability(self, dz_input: DZInput) -> Tuple[float, List[str]]:
        """
        Compute the situational reliability of the TSR sensor (SRD Novelty).
        
        TSR (Camera-based) performance degrades in specific environmental contexts.
        Returns a discount factor [0, 1] and a list of reasons.
        """
        reliability = 1.0
        reasons = []
        
        weather = dz_input.weather_condition.lower()
        surface = dz_input.road_surface.lower()
        
        # 1. Light Conditions
        if "night" in weather or "dark" in weather:
            reliability *= 0.7
            reasons.append("Reduced visibility at night (-30%)")
        
        # 2. Precipitation
        if "heavy rain" in weather or "storm" in weather:
            reliability *= 0.6
            reasons.append("Heavy rain blurring lens/obstructing view (-40%)")
        elif "rain" in weather:
            reliability *= 0.85
            reasons.append("Light rain / mist (-15%)")
            
        # 3. Fog/Vapor
        if "fog" in weather or "mist" in weather:
            reliability *= 0.65
            reasons.append("Fog/Haze reducing structural contrast (-35%)")
            
        # 4. Surface Spray (if fast on wet road)
        if surface == "wet" and dz_input.speed_kph > 60:
            reliability *= 0.9
            reasons.append("Road spray from preceding vehicles (-10%)")
            
        return max(0.1, reliability), reasons
        
    def _compute_adaptive_weights(
        self,
        dz_confidence: float,
        tsr_avg_confidence: float,
        num_signs: int
    ) -> Dict:
        """
        Compute adaptive evidence weights based on module confidence.
        
        When TSR has low confidence or no signs, reduce its influence.
        When TSR has many high-confidence signs, boost its weight.
        
        Returns:
            Dict with tsr, dz weights and reason string
        """
        if not self.adaptive_weighting:
            return {
                "tsr": round(self.base_tsr_weight, 3),
                "dz": round(self.base_dz_weight, 3),
                "mode": "fixed"
            }
        
        tsr_w = self.base_tsr_weight
        dz_w = self.base_dz_weight
        reason = "baseline"
        
        # Factor 1: TSR confidence scaling
        if num_signs == 0:
            # No signs detected — TSR contributes nothing
            tsr_w = 0.0
            reason = "no_signs"
        elif tsr_avg_confidence < 0.5:
            # Low confidence — reduce TSR
            tsr_w *= tsr_avg_confidence / 0.5  # linear scale down
            reason = "low_tsr_confidence"
        elif tsr_avg_confidence > 0.85 and num_signs >= 2:
            # High confidence + multiple signs — boost TSR
            boost = min(num_signs * 0.05, 0.15)
            tsr_w = min(tsr_w + boost, 0.50)  # cap at 50%
            reason = "high_tsr_confidence"
        
        # Factor 2: DZ confidence influence
        if dz_confidence > 0.9:
            # Very high DZ confidence — ensure it stays dominant
            dz_w = max(dz_w, 0.60)
            reason += "+strong_dz"
        
        # Normalise to sum to 1.0
        total = tsr_w + dz_w
        if total > 0:
            tsr_w /= total
            dz_w /= total
        else:
            dz_w = 1.0
            tsr_w = 0.0
        
        return {
            "tsr": round(tsr_w, 3),
            "dz": round(dz_w, 3),
            "mode": reason
        }
    
    # ─── Time-of-Day Context ───────────────────────────────────────────
    
    def _is_peak_hour(self, timestamp: float) -> bool:
        """
        Check if the current time falls within configured peak hours.
        
        Default peak hours (Colombo traffic):
          - Morning: 7:00 – 9:00
          - Evening: 16:30 – 19:00
        """
        dt = datetime.fromtimestamp(timestamp)
        current_minutes = dt.hour * 60 + dt.minute
        
        for start_h, start_m, end_h, end_m in self.peak_hours:
            start = start_h * 60 + start_m
            end = end_h * 60 + end_m
            if start <= current_minutes <= end:
                return True
        return False
    
    # ─── Segment History / Historical Learning ─────────────────────────
    
    def _segment_key(self, lat: float, lon: float) -> str:
        """Round lat/lon to grid cell (~100m precision)."""
        p = self._segment_grid_precision
        return f"{round(lat, p)},{round(lon, p)}"
    
    def _update_segment_history(
        self,
        speed: float,
        lat: float,
        lon: float,
        risk_score: float,
        conflict: float,
        timestamp: str
    ) -> None:
        """
        Update per-segment statistics for historical learning.
        
        Tracks average risk, conflict rate, and prediction count
        per ~100m grid cell.  When a segment accumulates enough
        predictions with consistently high conflict, it signals
        potential calibration issues.
        """
        if lat == 0 and lon == 0:
            return  # Skip unknown locations
        
        key = self._segment_key(lat, lon)
        
        if key not in self._segment_history:
            self._segment_history[key] = {
                "lat": lat,
                "lon": lon,
                "avg_risk": 0.0,
                "max_risk": 0.0,
                "conflict_sum": 0.0,
                "high_conflict_count": 0,
                "prediction_count": 0,
                "last_seen": timestamp
            }
        
        seg = self._segment_history[key]
        n = seg["prediction_count"]
        seg["avg_risk"] = (seg["avg_risk"] * n + risk_score) / (n + 1)
        seg["max_risk"] = max(seg["max_risk"], risk_score)
        seg["conflict_sum"] += conflict
        if conflict > self.conflict_threshold:
            seg["high_conflict_count"] += 1
        seg["prediction_count"] = n + 1
        seg["last_seen"] = timestamp
        
        # Warn about systematic calibration issues
        if seg["prediction_count"] >= 10:
            conflict_rate = seg["high_conflict_count"] / seg["prediction_count"]
            if conflict_rate > 0.30:
                logger.warning(
                    f"Segment ({lat:.3f}, {lon:.3f}) has {conflict_rate:.0%} conflict rate "
                    f"over {seg['prediction_count']} predictions — possible calibration issue"
                )
    
    def get_segment_insights(self) -> List[Dict]:
        """
        Get accumulated segment-level insights.
        
        Returns segments with enough data (>5 predictions),
        ordered by average risk score descending.
        """
        insights = []
        for key, seg in self._segment_history.items():
            if seg["prediction_count"] < 5:
                continue
            conflict_rate = seg["high_conflict_count"] / seg["prediction_count"]
            insights.append({
                "segment": key,
                "lat": seg["lat"],
                "lon": seg["lon"],
                "avg_risk": round(seg["avg_risk"], 1),
                "max_risk": round(seg["max_risk"], 1),
                "conflict_rate": round(conflict_rate, 3),
                "prediction_count": seg["prediction_count"],
                "needs_calibration": conflict_rate > 0.30,
                "last_seen": seg["last_seen"]
            })
        
        insights.sort(key=lambda x: x["avg_risk"], reverse=True)
        return insights
    
    @staticmethod
    def _weather_str_to_code(weather_str: str) -> int:
        """Convert weather description string to DZ weather code."""
        mapping = {
            "Fine": 1,
            "Rain": 2,
            "Snow": 3,
            "Fine + Wind": 4,
            "Rain + Wind": 5,
            "Snow + Wind": 6,
            "Fog/Mist": 7,
            "Fog": 7,
            "Other": 8,
            "Unknown": 9
        }
        return mapping.get(weather_str, 1)
