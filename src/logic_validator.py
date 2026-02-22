import logging
from typing import List, Dict, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

class ValidationStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    PLAUSIBLE = "PLAUSIBLE"
    QUESTIONABLE = "QUESTIONABLE"
    CONTRADICTION = "CONTRADICTION"
    RULE_OVERRIDE = "RULE_OVERRIDE"

class LogicValidator:
    """
    Neuro-Symbolic Logic Validator (NSLV Novelty).
    
    Cross-validates Neural TSR detections against Symbolic Road Rules 
    and Geographic Context. Provides an additional safety layer that can
    override neural uncertainty with deterministic logic.
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        
    def validate_detection(
        self, 
        class_name: str, 
        confidence: float, 
        speed_kph: float,
        road_type: str = "unknown"
    ) -> Tuple[ValidationStatus, str]:
        """
        Validate a sign detection against symbolic rules.
        
        Returns:
            (ValidationStatus, reason)
        """
        name = class_name.lower()
        
        # Rule 1: Speed Limit Consistency
        if "limit" in name:
            try:
                # Extract numerical limit (e.g., "speed_limit_50")
                limit = int(''.join(filter(str.isdigit, name)))
                
                # Overspeeding logic (Symbolic Veto)
                if speed_kph > limit + 10:
                    return ValidationStatus.CONTRADICTION, f"Detection '{class_name}' contradicts current speed of {speed_kph:.1f} kph"
                
                # Urban/Residential sanity check
                if limit >= 80 and road_type in ("residential", "living_street", "pedestrian"):
                    return ValidationStatus.QUESTIONABLE, f"High speed limit '{class_name}' is unlikely in {road_type} zone"
                    
            except ValueError:
                pass

        # Rule 2: Critical Safety "Veto" (Sign vs Speed)
        if "stop" in name and speed_kph > 40:
            return ValidationStatus.QUESTIONABLE, "STOP sign detected at high speed; possible false positive or high-risk approach"
            
        if "no_entry" in name and speed_kph > 20:
             return ValidationStatus.RULE_OVERRIDE, "Critical Hazard: NO ENTRY sign detected while moving. Immediate risk assessment required."

        # Rule 3: Minimum Confidence for Critical Signs
        critical_signs = ["stop", "no_entry", "wrong_way", "give_way"]
        if any(c in name for c in critical_signs) and confidence < 0.6:
            return ValidationStatus.QUESTIONABLE, f"Low-confidence detection of critical sign '{class_name}'"

        # Default to plausible if no contradictions found
        if confidence > 0.85:
            return ValidationStatus.CONFIRMED, "Neural detection validated by symbolic logic"
            
        return ValidationStatus.PLAUSIBLE, "No symbolic contradictions found"

    def get_risk_adjustment(self, status: ValidationStatus) -> float:
        """
        Returns a modifier for the risk based on validation status.
        Status-based multiplier for the final sign risk.
        """
        multipliers = {
            ValidationStatus.CONFIRMED: 1.1,      # Boost certainty
            ValidationStatus.PLAUSIBLE: 1.0,      # No change
            ValidationStatus.QUESTIONABLE: 0.6,   # Discount due to doubt
            ValidationStatus.CONTRADICTION: 0.2,  # Heavy discount (likely FP)
            ValidationStatus.RULE_OVERRIDE: 1.5,  # Force critical risk
        }
        return multipliers.get(status, 1.0)
