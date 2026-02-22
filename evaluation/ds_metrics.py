"""
Dempster-Shafer Uncertainty Metrics — Research Evaluation Script

Computes information-theoretic measures for belief function quality:
- NonSpecificity: Measures granularity/vagueness of the BPA
- Strife: Measures internal disagreement within a BPA
- Total Uncertainty: Combined measure (NS + Strife)
- Belief Interval Width: Precision of danger assessment

References:
    Klir, G.J. & Wierman, M.J. (1999). Uncertainty-Based Information.
    Springer. Chapter 5: Measures of Uncertainty.

    Jousselme, A.-L. et al. (2006). Measuring ambiguity in the evidence theory.
    IEEE Transactions on SMC-A, 36(5), 890-903.

Run: python -m evaluation.ds_metrics
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import json
from typing import Dict, List
from dataclasses import dataclass, asdict

from src.evidence import MassFunction, EvidenceConstructor, dempster_combine, murphy_combine
from src.fusion_engine import FusionEngine, TSRInput, DZInput, HotspotInput


# ─── Individual Metrics ──────────────────────────────────────────────

def nonspecificity(m: MassFunction) -> float:
    """
    Compute Generalized Hartley measure of NonSpecificity.
    
    NS(m) = Σ_A m(A) · log₂|A|
    
    For our frame {SAFE, DANGEROUS, Θ}:
    - |{SAFE}| = 1   → log₂(1) = 0
    - |{DANGEROUS}| = 1 → log₂(1) = 0
    - |{Θ}| = 2      → log₂(2) = 1
    
    Therefore: NS(m) = m(Θ) · 1 = m(Θ)
    
    Higher values indicate more vague/non-committal evidence.
    Range: [0, 1] for our binary frame.
    """
    return m.m_uncertain * math.log2(2)  # = m_uncertain


def strife(m: MassFunction) -> float:
    """
    Compute Strife measure of internal conflict within a BPA.
    
    For our frame {SAFE, DANGEROUS, Θ}, strife captures the degree
    to which the mass function distributes evidence to contradictory
    focal elements.
    
    We use a simplified form for our 3-element frame:
    
    Strife ≈ -Σ_A m(A) · log₂ [max_B (|A ∩ B| / |A|) weighted by m(B)]
    
    For practical computation with our frame:
    - When mass is concentrated on one hypothesis → strife ≈ 0
    - When mass is split between SAFE and DANGEROUS → strife is high
    
    Range: [0, 1]
    """
    if m.m_safe < 1e-10 and m.m_dangerous < 1e-10:
        return 0.0  # Pure ignorance — no strife
    
    committed = m.m_safe + m.m_dangerous
    if committed < 1e-10:
        return 0.0
    
    # Normalized distribution over committed focal elements
    p_safe = m.m_safe / (committed + 1e-10)
    p_dangerous = m.m_dangerous / (committed + 1e-10)
    
    # Shannon entropy of the committed distribution
    entropy = 0.0
    if p_safe > 1e-10:
        entropy -= p_safe * math.log2(p_safe)
    if p_dangerous > 1e-10:
        entropy -= p_dangerous * math.log2(p_dangerous)
    
    # Scale by the committed mass (strife is 0 when everything is uncertain)
    return entropy * committed


def total_uncertainty(m: MassFunction) -> float:
    """
    Total Uncertainty = NonSpecificity + Strife.
    
    Combined measure capturing both vagueness (NS) and conflict (Strife).
    Range: [0, 2] theoretically, but typically [0, 1.5] in practice.
    """
    return nonspecificity(m) + strife(m)


def belief_interval_width(m: MassFunction) -> float:
    """
    Width of the belief interval for DANGEROUS: Pl(D) - Bel(D) = m(Θ).
    
    Narrower intervals indicate more precise risk assessment.
    Range: [0, 1]
    """
    return m.plausibility_dangerous - m.belief_dangerous


def pignistic_entropy(m: MassFunction) -> float:
    """
    Entropy of the pignistic probability distribution.
    
    H(BetP) = -BetP(D)·log₂(BetP(D)) - BetP(S)·log₂(BetP(S))
    
    High entropy → decision maker has less certainty about the outcome.
    Range: [0, 1] for binary frame.
    """
    p_d = m.pignistic_probability
    p_s = 1.0 - p_d
    
    entropy = 0.0
    if p_d > 1e-10:
        entropy -= p_d * math.log2(p_d)
    if p_s > 1e-10:
        entropy -= p_s * math.log2(p_s)
    
    return entropy


def compute_all_metrics(m: MassFunction) -> Dict[str, float]:
    """
    Compute all DS uncertainty metrics for a given mass function.
    
    Returns:
        Dict with keys: nonspecificity, strife, total_uncertainty,
                        belief_interval_width, pignistic_entropy
    """
    return {
        "nonspecificity": round(nonspecificity(m), 6),
        "strife": round(strife(m), 6),
        "total_uncertainty": round(total_uncertainty(m), 6),
        "belief_interval_width": round(belief_interval_width(m), 6),
        "pignistic_entropy": round(pignistic_entropy(m), 6),
    }


# ─── Evaluation Scenarios ────────────────────────────────────────────

@dataclass
class MetricScenario:
    name: str
    dz_score: float
    dz_confidence: float
    tsr_class_id: int
    tsr_class_name: str
    tsr_confidence: float
    weather: str
    road_surface: str
    speed_kph: float

SCENARIOS = [
    MetricScenario("Curve in Rain", 42, 0.88, 87, "curve_to_left", 0.94, "Rain", "Wet", 55),
    MetricScenario("Safe + Parking", 15, 0.90, 13, "parking", 0.95, "Fine", "Dry", 30),
    MetricScenario("High Risk + Accident", 75, 0.92, 83, "accident", 0.95, "Fine", "Dry", 60),
    MetricScenario("School Zone", 45, 0.85, 68,
                   "maximum_speed_limit_(all_vehicles_within_school_areas_and_hospitals)",
                   0.88, "Fine", "Dry", 35),
    MetricScenario("Slippery in Rain", 50, 0.86, 112, "slippery_road", 0.90, "Rain", "Wet", 50),
    MetricScenario("Night Level Crossing", 55, 0.84, 102,
                   "level_crossing_without_barriers_ahead", 0.87, "Dark", "Dry", 45),
    MetricScenario("DZ-only High", 80, 0.95, -1, "", 0.0, "Fine", "Dry", 60),
    MetricScenario("DZ-only Low", 10, 0.92, -1, "", 0.0, "Fine", "Dry", 30),
]


def _level(score: float) -> str:
    if score >= 65: return "HIGH"
    if score >= 35: return "MEDIUM"
    return "LOW"


def run_metrics_evaluation():
    """Run DS uncertainty metrics across all scenarios."""
    
    print("=" * 90)
    print("DEMPSTER-SHAFER UNCERTAINTY METRICS EVALUATION")
    print("=" * 90)
    
    all_results = []
    
    # Header
    print(f"\n{'Scenario':<25} {'NS':>6} {'Strife':>8} {'TU':>6} "
          f"{'BI Width':>9} {'PigEnt':>7} {'Score':>6} {'Level':>6}")
    print("─" * 85)
    
    for s in SCENARIOS:
        engine = FusionEngine()
        
        dz = DZInput(
            risk_score=s.dz_score,
            risk_level=_level(s.dz_score),
            confidence=s.dz_confidence,
            risk_probability=s.dz_score / 100.0,
            weather_condition=s.weather,
            road_surface=s.road_surface,
            speed_kph=s.speed_kph
        )
        
        tsr = None
        if s.tsr_class_id >= 0 and s.tsr_confidence > 0:
            tsr = TSRInput(
                class_id=s.tsr_class_id,
                class_name=s.tsr_class_name,
                confidence=s.tsr_confidence,
                is_confident=True
            )
        
        result = engine.fuse(dz_input=dz, tsr_input=tsr)
        
        # Get the fused mass function from the result
        fused_mass = MassFunction(
            m_safe=result.mass_safe if hasattr(result, 'mass_safe') else (1 - result.pignistic_probability - result.uncertainty_width / 2),
            m_dangerous=result.belief_dangerous,
            m_uncertain=result.uncertainty_width,
            source="fused"
        )
        
        metrics = compute_all_metrics(fused_mass)
        
        row = {
            "scenario": s.name,
            "fused_score": result.fused_risk_score,
            "fused_level": result.fused_risk_level,
            **metrics
        }
        all_results.append(row)
        
        print(f"{s.name:<25} {metrics['nonspecificity']:>6.3f} {metrics['strife']:>8.3f} "
              f"{metrics['total_uncertainty']:>6.3f} {metrics['belief_interval_width']:>9.3f} "
              f"{metrics['pignistic_entropy']:>7.3f} {result.fused_risk_score:>6.1f} "
              f"{result.fused_risk_level:>6}")
    
    # Summary statistics
    print(f"\n{'=' * 90}")
    print("SUMMARY STATISTICS")
    print(f"{'=' * 90}")
    
    metric_keys = ["nonspecificity", "strife", "total_uncertainty",
                    "belief_interval_width", "pignistic_entropy"]
    
    print(f"\n{'Metric':<25} {'Mean':>8} {'Min':>8} {'Max':>8} {'Std':>8}")
    print("─" * 57)
    
    for key in metric_keys:
        values = [r[key] for r in all_results]
        mean = sum(values) / len(values)
        mn = min(values)
        mx = max(values)
        std = (sum((v - mean)**2 for v in values) / len(values)) ** 0.5
        print(f"{key:<25} {mean:>8.4f} {mn:>8.4f} {mx:>8.4f} {std:>8.4f}")
    
    # Comparison: Dempster vs Murphy
    print(f"\n{'=' * 90}")
    print("DEMPSTER vs MURPHY: UNCERTAINTY COMPARISON")
    print(f"{'=' * 90}")
    
    comparison = []
    
    print(f"\n{'Scenario':<25} {'DS-TU':>7} {'MU-TU':>7} {'DS-BI':>7} {'MU-BI':>7} "
          f"{'DS-Ent':>7} {'MU-Ent':>7}")
    print("─" * 67)
    
    for s in SCENARIOS:
        if s.tsr_class_id < 0:
            continue  # Skip DZ-only scenarios
            
        # Build mass functions manually for comparison
        dz_mass = EvidenceConstructor.from_dz(s.dz_score / 100.0, s.dz_confidence)
        
        ontology = FusionEngine().ontology
        profile = ontology.get_profile(s.tsr_class_id)
        modifier = profile.base_risk_modifier if profile else 0
        tsr_mass = EvidenceConstructor.from_tsr(modifier, s.tsr_confidence)
        
        # Dempster combination
        ds_combined, ds_K = dempster_combine(dz_mass, tsr_mass)
        ds_metrics = compute_all_metrics(ds_combined)
        
        # Murphy combination
        mu_combined, mu_K = murphy_combine([dz_mass, tsr_mass])
        mu_metrics = compute_all_metrics(mu_combined)
        
        comparison.append({
            "scenario": s.name,
            "ds_metrics": ds_metrics,
            "murphy_metrics": mu_metrics,
            "ds_conflict": ds_K,
            "murphy_conflict": mu_K,
        })
        
        print(f"{s.name:<25} "
              f"{ds_metrics['total_uncertainty']:>7.3f} {mu_metrics['total_uncertainty']:>7.3f} "
              f"{ds_metrics['belief_interval_width']:>7.3f} {mu_metrics['belief_interval_width']:>7.3f} "
              f"{ds_metrics['pignistic_entropy']:>7.3f} {mu_metrics['pignistic_entropy']:>7.3f}")
    
    # Save results
    output = {
        "scenario_metrics": all_results,
        "dempster_vs_murphy": comparison,
    }
    
    with open("evaluation/ds_metrics_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to evaluation/ds_metrics_results.json")


if __name__ == "__main__":
    run_metrics_evaluation()
