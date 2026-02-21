"""
Evidence Module — Dempster-Shafer Mass Functions & Evidence Frames

Implements the mathematical foundation for belief function fusion:
- MassFunction: Represents basic probability assignments (BPA) over {SAFE, DANGEROUS, Θ}
- EvidenceFrame: Converts TSR/DZ module outputs into mass functions
- Dempster's Rule of Combination with conflict handling

Theory Reference:
  Shafer, G. (1976). A Mathematical Theory of Evidence. Princeton University Press.
  Dempster, A.P. (1967). Upper and lower probabilities induced by a multivalued mapping.
    Annals of Mathematical Statistics, 38(2), 325-339.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple
from enum import Enum


class Hypothesis(Enum):
    """Frame of discernment for road safety assessment."""
    SAFE = "safe"             # Road segment is safe
    DANGEROUS = "dangerous"   # Road segment is dangerous
    UNCERTAIN = "uncertain"   # Θ (theta) — complete ignorance


@dataclass
class MassFunction:
    """
    Basic Probability Assignment (BPA) over the frame of discernment.
    
    A mass function m assigns belief masses to subsets of {SAFE, DANGEROUS, Θ}:
    - m({SAFE}): Evidence supporting safety
    - m({DANGEROUS}): Evidence supporting danger
    - m({Θ}): Residual uncertainty / ignorance
    
    Constraint: m(SAFE) + m(DANGEROUS) + m(UNCERTAIN) = 1.0
    
    Attributes:
        m_safe: Mass assigned to {SAFE}
        m_dangerous: Mass assigned to {DANGEROUS}  
        m_uncertain: Mass assigned to {Θ} (ignorance/uncommitted)
        source: Identifier for the evidence source
    """
    m_safe: float = 0.0
    m_dangerous: float = 0.0
    m_uncertain: float = 1.0  # Default: complete ignorance
    source: str = "unknown"
    
    def __post_init__(self):
        """Validate and normalize mass assignments."""
        total = self.m_safe + self.m_dangerous + self.m_uncertain
        if abs(total - 1.0) > 1e-6:
            # Normalize
            if total > 0:
                self.m_safe /= total
                self.m_dangerous /= total
                self.m_uncertain /= total
            else:
                self.m_uncertain = 1.0
        
        # Clamp to valid range
        self.m_safe = max(0.0, min(1.0, self.m_safe))
        self.m_dangerous = max(0.0, min(1.0, self.m_dangerous))
        self.m_uncertain = max(0.0, min(1.0, self.m_uncertain))
    
    @property
    def belief_safe(self) -> float:
        """Belief (lower bound probability) for SAFE."""
        return self.m_safe
    
    @property
    def belief_dangerous(self) -> float:
        """Belief (lower bound probability) for DANGEROUS."""
        return self.m_dangerous
    
    @property
    def plausibility_safe(self) -> float:
        """Plausibility (upper bound probability) for SAFE."""
        return self.m_safe + self.m_uncertain
    
    @property
    def plausibility_dangerous(self) -> float:
        """Plausibility (upper bound probability) for DANGEROUS."""
        return self.m_dangerous + self.m_uncertain
    
    @property
    def pignistic_probability(self) -> float:
        """
        Pignistic (betting) probability of DANGEROUS.
        
        Transforms the belief interval [Bel(D), Pl(D)] into a point estimate
        using the pignistic transform (Smets, 2005):
        
        BetP(D) = m(D) + m(Θ) × m(D) / (m(S) + m(D))
        
        When m(S) + m(D) = 0, defaults to 0.5 (maximum ignorance).
        """
        committed = self.m_safe + self.m_dangerous
        if committed < 1e-10:
            return 0.5  # Complete ignorance → uniform
        
        return self.m_dangerous + self.m_uncertain * (self.m_dangerous / committed)
    
    @property
    def uncertainty_width(self) -> float:
        """
        Width of the belief interval for DANGEROUS.
        
        Pl(D) - Bel(D) = m(Θ)
        
        Higher values indicate more uncertainty.
        """
        return self.m_uncertain
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "m_safe": round(self.m_safe, 6),
            "m_dangerous": round(self.m_dangerous, 6),
            "m_uncertain": round(self.m_uncertain, 6),
            "source": self.source,
            "belief_dangerous": round(self.belief_dangerous, 6),
            "plausibility_dangerous": round(self.plausibility_dangerous, 6),
            "pignistic_probability": round(self.pignistic_probability, 6)
        }


def dempster_combine(m1: MassFunction, m2: MassFunction) -> Tuple[MassFunction, float]:
    """
    Combine two mass functions using Dempster's Rule of Combination.
    
    The combination rule computes the joint mass function from two
    independent evidence sources, with normalization by the conflict factor.
    
    For focal elements A, B:
        m₁₂(C) = [Σ_{A∩B=C} m₁(A)·m₂(B)] / (1 - K)
    
    where K = Σ_{A∩B=∅} m₁(A)·m₂(B) is the degree of conflict.
    
    Args:
        m1: First mass function
        m2: Second mass function
        
    Returns:
        Tuple of (combined MassFunction, conflict measure K)
        
    Raises:
        ValueError: If conflict K ≥ 1.0 (complete contradiction)
    """
    # Compute all pairwise intersections
    # Focal elements: {S}, {D}, {Θ}
    # Intersections:
    #   {S} ∩ {S} = {S},  {S} ∩ {D} = ∅,   {S} ∩ {Θ} = {S}
    #   {D} ∩ {S} = ∅,    {D} ∩ {D} = {D},  {D} ∩ {Θ} = {D}
    #   {Θ} ∩ {S} = {S},  {Θ} ∩ {D} = {D},  {Θ} ∩ {Θ} = {Θ}
    
    # Conflict mass (intersections that produce empty set)
    K = (m1.m_safe * m2.m_dangerous +   # SAFE ∩ DANGEROUS = ∅
         m1.m_dangerous * m2.m_safe)      # DANGEROUS ∩ SAFE = ∅
    
    if K >= 1.0 - 1e-10:
        # Near-total conflict: fall back to uncertainty
        return MassFunction(
            m_safe=0.0,
            m_dangerous=0.0,
            m_uncertain=1.0,
            source=f"{m1.source}+{m2.source}(conflict)"
        ), K
    
    norm = 1.0 / (1.0 - K)
    
    # Combined masses (unnormalized intersections)
    m_safe = norm * (
        m1.m_safe * m2.m_safe +           # {S} ∩ {S} = {S}
        m1.m_safe * m2.m_uncertain +       # {S} ∩ {Θ} = {S}
        m1.m_uncertain * m2.m_safe          # {Θ} ∩ {S} = {S}
    )
    
    m_dangerous = norm * (
        m1.m_dangerous * m2.m_dangerous +   # {D} ∩ {D} = {D}
        m1.m_dangerous * m2.m_uncertain +   # {D} ∩ {Θ} = {D}
        m1.m_uncertain * m2.m_dangerous      # {Θ} ∩ {D} = {D}
    )
    
    m_uncertain = norm * (
        m1.m_uncertain * m2.m_uncertain     # {Θ} ∩ {Θ} = {Θ}
    )
    
    combined = MassFunction(
        m_safe=m_safe,
        m_dangerous=m_dangerous,
        m_uncertain=m_uncertain,
        source=f"{m1.source}⊕{m2.source}"
    )
    
    return combined, K


def combine_multiple(mass_functions: List[MassFunction]) -> Tuple[MassFunction, List[float]]:
    """
    Combine multiple mass functions sequentially using Dempster's Rule.
    
    Args:
        mass_functions: List of mass functions to combine
        
    Returns:
        Tuple of (final combined MassFunction, list of pairwise conflicts)
    """
    if not mass_functions:
        return MassFunction(source="empty"), []
    
    if len(mass_functions) == 1:
        return mass_functions[0], []
    
    result = mass_functions[0]
    conflicts = []
    
    for mf in mass_functions[1:]:
        result, K = dempster_combine(result, mf)
        conflicts.append(K)
    
    return result, conflicts


class EvidenceConstructor:
    """
    Converts raw module outputs into Dempster-Shafer mass functions.
    
    Handles two evidence sources:
    1. TSR (Traffic Sign Recognition) → visual perception evidence
    2. DZ (Dangerous Zone Prediction) → structured sensor/model evidence
    """
    
    @staticmethod
    def from_tsr(
        sign_risk_modifier: float,
        tsr_confidence: float,
        temporal_decay: float = 1.0,
        min_confidence: float = 0.5
    ) -> MassFunction:
        """
        Construct mass function from TSR module output.
        
        The sign risk modifier (from ontology) determines the direction of evidence,
        while TSR confidence and temporal decay determine the strength.
        
        For hazard signs (modifier > 0):
            m({DANGEROUS}) = modifier × confidence × decay
            m({SAFE}) = (1 - modifier) × confidence × decay × 0.5
            m({Θ}) = 1 - m(D) - m(S)
        
        Args:
            sign_risk_modifier: From SignRiskOntology [0, 1]
            tsr_confidence: Model prediction confidence [0, 1]
            temporal_decay: Time decay factor [0, 1]
            min_confidence: Minimum TSR confidence to form evidence
            
        Returns:
            MassFunction representing TSR evidence
        """
        # Below confidence threshold → pure ignorance
        if tsr_confidence < min_confidence:
            return MassFunction(source="tsr(low_conf)")
        
        # Effective evidence strength
        strength = tsr_confidence * temporal_decay
        
        # High modifier → evidence of danger
        # Low modifier → evidence of relative safety
        if sign_risk_modifier > 0.15:
            # Hazard/regulatory sign → evidence of danger
            m_dangerous = sign_risk_modifier * strength
            m_safe = (1.0 - sign_risk_modifier) * strength * 0.3  # Slight counter-evidence
            m_uncertain = 1.0 - m_dangerous - m_safe
        elif sign_risk_modifier < 0.05:
            # Purely informational sign → weak evidence of safety
            m_safe = (1.0 - sign_risk_modifier) * strength * 0.2
            m_dangerous = 0.0
            m_uncertain = 1.0 - m_safe
        else:
            # Mild sign → mostly ignorance
            m_dangerous = sign_risk_modifier * strength * 0.5
            m_safe = (1.0 - sign_risk_modifier) * strength * 0.2
            m_uncertain = 1.0 - m_dangerous - m_safe
        
        # Ensure non-negative
        m_uncertain = max(0.0, m_uncertain)
        
        return MassFunction(
            m_safe=m_safe,
            m_dangerous=m_dangerous,
            m_uncertain=m_uncertain,
            source="tsr"
        )
    
    @staticmethod
    def from_dz(
        risk_probability: float,
        dz_confidence: float,
        min_confidence: float = 0.3
    ) -> MassFunction:
        """
        Construct mass function from DZ module output.
        
        The DZ risk probability directly indicates danger level,
        discounted by the DZ module's confidence score.
        
        Args:
            risk_probability: DZ ensemble probability [0, 1]
            dz_confidence: DZ confidence score [0, 1]
            min_confidence: Minimum DZ confidence to form evidence
            
        Returns:
            MassFunction representing DZ evidence
        """
        if dz_confidence < min_confidence:
            return MassFunction(source="dz(low_conf)")
        
        # Scale evidence by confidence
        effective = dz_confidence
        
        m_dangerous = risk_probability * effective
        m_safe = (1.0 - risk_probability) * effective
        m_uncertain = 1.0 - m_dangerous - m_safe
        
        # Ensure non-negative
        m_uncertain = max(0.0, m_uncertain)
        
        return MassFunction(
            m_safe=m_safe,
            m_dangerous=m_dangerous,
            m_uncertain=m_uncertain,
            source="dz"
        )
    
    @staticmethod
    def from_hotspot(
        risk_boost: float,
        report_count: int,
        max_reports_for_full_confidence: int = 10
    ) -> MassFunction:
        """
        Construct mass function from crowdsourced accident hotspot data.
        
        Args:
            risk_boost: Base risk boost from hotspot DB [0, 1]
            report_count: Number of reports at this location
            max_reports_for_full_confidence: Reports needed for max confidence
            
        Returns:
            MassFunction representing hotspot evidence
        """
        if risk_boost <= 0 or report_count <= 0:
            return MassFunction(source="hotspot(none)")
        
        # Confidence grows with report count (saturating)
        confidence = min(report_count / max_reports_for_full_confidence, 1.0)
        
        m_dangerous = risk_boost * confidence
        m_safe = 0.0  # Hotspots only provide danger evidence
        m_uncertain = 1.0 - m_dangerous
        
        return MassFunction(
            m_safe=m_safe,
            m_dangerous=m_dangerous,
            m_uncertain=m_uncertain,
            source="hotspot"
        )
