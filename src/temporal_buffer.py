"""
Temporal Sign Buffer Module
Manages a sliding window of recently detected traffic signs with
exponential time-decay for evidence aggregation.

The buffer accumulates TSR detections over time and computes aggregate
sign evidence by combining all active (non-expired) detections. This
enables the fusion engine to consider the cumulative context of signs
encountered along a route segment, not just the most recent detection.

Features:
- Exponential decay: weight(t) = exp(-λ × Δt)
- Configurable buffer size and max age
- Sign sequence detection (compounding evidence)
- Thread-safe for concurrent access
"""

import time
import math
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import deque


@dataclass
class SignDetection:
    """
    A single traffic sign detection event.
    
    Attributes:
        class_id: TSR model class index (0-121)
        class_name: Human-readable sign name
        confidence: TSR prediction confidence [0, 1]
        timestamp: Detection time (seconds since epoch)
        latitude: GPS latitude at detection
        longitude: GPS longitude at detection
        risk_modifier: Effective risk modifier from ontology (context-adjusted)
        relevance_duration_s: How long this sign remains relevant
    """
    class_id: int
    class_name: str
    confidence: float
    timestamp: float
    latitude: float = 0.0
    longitude: float = 0.0
    risk_modifier: float = 0.0
    relevance_duration_s: float = 15.0


@dataclass
class AggregateSignEvidence:
    """
    Aggregated evidence from all active signs in the buffer.
    
    Attributes:
        max_risk_modifier: Highest active risk modifier (dominates danger)
        weighted_avg_modifier: Decay-weighted average risk modifier
        num_active_signs: Number of non-expired signs
        dominant_sign: The sign with highest current weighted contribution
        active_categories: Set of active sign risk categories
        compound_factor: Multiplier from sign sequences (e.g., curve + speed limit)
        total_decay_weight: Sum of all decay weights (measure of evidence freshness)
    """
    max_risk_modifier: float = 0.0
    weighted_avg_modifier: float = 0.0
    num_active_signs: int = 0
    dominant_sign: Optional[SignDetection] = None
    active_categories: List[str] = field(default_factory=list)
    compound_factor: float = 1.0
    total_decay_weight: float = 0.0
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "max_risk_modifier": round(self.max_risk_modifier, 4),
            "weighted_avg_modifier": round(self.weighted_avg_modifier, 4),
            "num_active_signs": self.num_active_signs,
            "dominant_sign": self.dominant_sign.class_name if self.dominant_sign else None,
            "active_categories": self.active_categories,
            "compound_factor": round(self.compound_factor, 4),
            "total_decay_weight": round(self.total_decay_weight, 4)
        }


# Known compounding sign pairs that amplify risk when seen together
COMPOUND_PAIRS = {
    # (category1, category2) → compound multiplier
    ("hazard_warning", "speed_regulatory"): 1.3,    # Curve + Speed limit
    ("hazard_warning", "priority"): 1.4,            # Hazard + Give way/Stop
    ("hazard_warning", "hazard_warning"): 1.2,      # Multiple hazards
    ("prohibition", "hazard_warning"): 1.3,         # No overtaking + Curve
    ("traffic_signal", "hazard_warning"): 1.2,      # Red light + Hazard
    ("speed_regulatory", "priority"): 1.2,          # Speed limit + Stop
}


class TemporalSignBuffer:
    """
    Sliding window buffer for traffic sign detections with time-decay.
    
    Usage:
        buffer = TemporalSignBuffer(decay_lambda=0.1, max_age_s=60)
        buffer.add(SignDetection(class_id=88, class_name="curve_to_left", ...))
        evidence = buffer.get_aggregate_evidence()
    """
    
    def __init__(
        self,
        decay_lambda: float = 0.1,
        max_signs: int = 20,
        max_age_s: float = 60.0
    ):
        """
        Initialize temporal buffer.
        
        Args:
            decay_lambda: Exponential decay rate (higher = faster decay)
            max_signs: Maximum number of signs to retain
            max_age_s: Maximum age in seconds before a sign is evicted
        """
        self.decay_lambda = decay_lambda
        self.max_signs = max_signs
        self.max_age_s = max_age_s
        self._buffer: deque = deque(maxlen=max_signs)
        self._lock = threading.Lock()
    
    def add(self, detection: SignDetection) -> None:
        """
        Add a new sign detection to the buffer.
        
        Deduplicates: if the same sign class was detected within the last 2 seconds,
        the existing detection is updated with the higher confidence.
        """
        with self._lock:
            # Deduplication check
            for existing in self._buffer:
                if (existing.class_id == detection.class_id and
                    abs(existing.timestamp - detection.timestamp) < 2.0):
                    # Update confidence if new detection is better
                    if detection.confidence > existing.confidence:
                        existing.confidence = detection.confidence
                        existing.timestamp = detection.timestamp
                        existing.risk_modifier = detection.risk_modifier
                    return
            
            self._buffer.append(detection)
    
    def get_active_detections(self, current_time: Optional[float] = None) -> List[SignDetection]:
        """
        Get all non-expired sign detections.
        
        Args:
            current_time: Current time in seconds since epoch (defaults to now)
            
        Returns:
            List of active (non-expired) detections
        """
        now = current_time or time.time()
        
        with self._lock:
            active = []
            for det in self._buffer:
                age = now - det.timestamp
                # Expired by max age or by sign-specific relevance duration
                max_age = min(self.max_age_s, det.relevance_duration_s * 3)
                if age <= max_age:
                    active.append(det)
            return active
    
    def compute_decay_weight(self, detection: SignDetection, current_time: Optional[float] = None) -> float:
        """
        Compute exponential decay weight for a detection.
        
        weight(t) = exp(-λ × Δt) × confidence
        
        Also considers the sign's relevance duration: signs past their
        relevance duration decay faster (2× lambda).
        """
        now = current_time or time.time()
        age = now - detection.timestamp
        
        if age < 0:
            return detection.confidence
        
        # After relevance duration, double the decay rate
        if age > detection.relevance_duration_s:
            effective_lambda = self.decay_lambda * 2.0
        else:
            effective_lambda = self.decay_lambda
        
        decay = math.exp(-effective_lambda * age)
        return decay * detection.confidence
    
    def get_aggregate_evidence(self, current_time: Optional[float] = None) -> AggregateSignEvidence:
        """
        Compute aggregate sign evidence from all active detections.
        
        Combines all decay-weighted sign risk modifiers into a single
        evidence summary for the fusion engine.
        
        Returns:
            AggregateSignEvidence with aggregated risk metrics
        """
        now = current_time or time.time()
        active = self.get_active_detections(now)
        
        if not active:
            return AggregateSignEvidence()
        
        # Compute weighted contributions
        weighted_modifiers = []
        decay_weights = []
        max_modifier = 0.0
        dominant = None
        dominant_contribution = 0.0
        categories = set()
        
        for det in active:
            weight = self.compute_decay_weight(det, now)
            weighted_mod = det.risk_modifier * weight
            
            weighted_modifiers.append(weighted_mod)
            decay_weights.append(weight)
            
            if weighted_mod > dominant_contribution:
                dominant_contribution = weighted_mod
                dominant = det
            
            if det.risk_modifier > max_modifier:
                max_modifier = det.risk_modifier
        
        total_weight = sum(decay_weights)
        
        # Weighted average modifier
        if total_weight > 0:
            weighted_avg = sum(weighted_modifiers) / total_weight
        else:
            weighted_avg = 0.0
        
        # Detect compound sign sequences
        compound_factor = self._compute_compound_factor(active)
        
        # Collect active categories (for evidence.py — deduced from modifier ranges)
        for det in active:
            if det.risk_modifier >= 0.3:
                categories.add("hazard_warning")
            elif det.risk_modifier >= 0.15:
                categories.add("regulatory")
            else:
                categories.add("informational")
        
        return AggregateSignEvidence(
            max_risk_modifier=max_modifier,
            weighted_avg_modifier=weighted_avg,
            num_active_signs=len(active),
            dominant_sign=dominant,
            active_categories=sorted(categories),
            compound_factor=compound_factor,
            total_decay_weight=total_weight
        )
    
    def _compute_compound_factor(self, active: List[SignDetection]) -> float:
        """
        Compute compounding factor from sign sequence patterns.
        
        When complementary signs appear together (e.g., curve + speed limit),
        their combined evidence is amplified.
        """
        if len(active) < 2:
            return 1.0
        
        # Categorize active signs
        sign_categories = set()
        for det in active:
            if det.risk_modifier >= 0.4:
                sign_categories.add("hazard_warning")
            elif det.risk_modifier >= 0.2:
                sign_categories.add("prohibition")
            elif det.risk_modifier >= 0.1:
                sign_categories.add("speed_regulatory")
            
            # Check specific sign types from name
            if "stop" in det.class_name or "give_way" in det.class_name:
                sign_categories.add("priority")
            if "traffic_light" in det.class_name or "red" in det.class_name:
                sign_categories.add("traffic_signal")
        
        # Find matching compound pairs
        max_compound = 1.0
        cats = list(sign_categories)
        for i in range(len(cats)):
            for j in range(i + 1, len(cats)):
                pair = (cats[i], cats[j])
                reverse_pair = (cats[j], cats[i])
                
                if pair in COMPOUND_PAIRS:
                    max_compound = max(max_compound, COMPOUND_PAIRS[pair])
                elif reverse_pair in COMPOUND_PAIRS:
                    max_compound = max(max_compound, COMPOUND_PAIRS[reverse_pair])
        
        return max_compound
    
    def clear(self) -> None:
        """Clear all detections (e.g., start of new trip)."""
        with self._lock:
            self._buffer.clear()
    
    def cleanup(self, current_time: Optional[float] = None) -> int:
        """
        Remove expired detections from the buffer.
        
        Returns:
            Number of detections removed
        """
        now = current_time or time.time()
        
        with self._lock:
            before = len(self._buffer)
            active = deque(maxlen=self.max_signs)
            for det in self._buffer:
                age = now - det.timestamp
                max_age = min(self.max_age_s, det.relevance_duration_s * 3)
                if age <= max_age:
                    active.append(det)
            self._buffer = active
            return before - len(self._buffer)
    
    @property
    def size(self) -> int:
        """Current number of detections in buffer."""
        return len(self._buffer)
