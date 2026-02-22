"""
Expanded Ablation Study — Research Evaluation Script

Compares fusion method variants with component-level ablation:
- DZ-only baseline
- Weighted Average baseline
- Dempster-Shafer (DS) Fusion (full system)
- Murphy's Rule Fusion (alternative combiner)
- DS without temporal buffer
- DS without adaptive weights
- DS without contextual rules

Run: python -m evaluation.ablation_study
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import statistics
from typing import List, Dict
from dataclasses import dataclass
from src.fusion_engine import FusionEngine, TSRInput, DZInput, HotspotInput
from src.evidence import (
    MassFunction, EvidenceConstructor, dempster_combine,
    murphy_combine, combine_multiple
)


@dataclass
class Scenario:
    """A test scenario with expected outcome direction."""
    name: str
    dz_score: float
    dz_confidence: float
    tsr_class_id: int
    tsr_class_name: str
    tsr_confidence: float
    weather: str
    road_surface: str
    speed_kph: float
    expected_direction: str  # "increase", "decrease", "maintain"
    description: str


# Representative test scenarios
SCENARIOS: List[Scenario] = [
    Scenario("Curve in Rain", 42, 0.88, 87, "curve_to_left", 0.94,
             "Rain", "Wet", 55, "increase",
             "Sharp curve on wet road → should amplify DZ risk"),
    Scenario("Safe Road + Parking", 15, 0.90, 13, "parking", 0.95,
             "Fine", "Dry", 30, "maintain",
             "Informational sign on safe road → minimal change"),
    Scenario("High Risk + Accident", 75, 0.92, 83, "accident", 0.95,
             "Fine", "Dry", 60, "increase",
             "Accident sign compounds existing high risk"),
    Scenario("Medium Risk + Speed Limit School", 45, 0.85, 68,
             "maximum_speed_limit_(all_vehicles_within_school_areas_and_hospitals)",
             0.88, "Fine", "Dry", 35, "increase",
             "School zone speed limit → heightened caution"),
    Scenario("Low Risk + Stop Sign", 25, 0.87, 39, "stop", 0.91,
             "Fine", "Dry", 40, "increase",
             "Stop sign indicates intersection → risk increase"),
    Scenario("Slippery Road in Rain", 50, 0.86, 112, "slippery_road", 0.90,
             "Rain", "Wet", 50, "increase",
             "Slippery road sign + rain = severe compound risk"),
    Scenario("Night Level Crossing", 55, 0.84, 102,
             "level_crossing_without_barriers_ahead", 0.87,
             "Dark", "Dry", 45, "increase",
             "Unprotected level crossing at night"),
    Scenario("Motorway Info", 30, 0.90, 2, "motorway", 0.96,
             "Fine", "Dry", 80, "maintain",
             "Motorway information sign → minimal impact"),
]


def _level(score: float) -> str:
    if score >= 65: return "HIGH"
    if score >= 35: return "MEDIUM"
    return "LOW"


def compute_directional_correctness(delta: float, expected: str) -> str:
    """Check whether the fusion result moved in the expected direction."""
    if expected == "increase" and delta > 0:
        return "OK"
    elif expected == "decrease" and delta < 0:
        return "OK"
    elif expected == "maintain" and abs(delta) < 10:
        return "OK"
    return "MISS"


# ─── Method Implementations ──────────────────────────────────────────

def fusion_dz_only(scenario: Scenario) -> float:
    """Variant 1: DZ-only baseline (no fusion)."""
    engine = FusionEngine()
    dz = DZInput(
        risk_score=scenario.dz_score,
        risk_level=_level(scenario.dz_score),
        confidence=scenario.dz_confidence,
        risk_probability=scenario.dz_score / 100.0,
        weather_condition=scenario.weather,
        road_surface=scenario.road_surface,
        speed_kph=scenario.speed_kph
    )
    return engine.fuse(dz_input=dz).fused_risk_score


def fusion_weighted_average(scenario: Scenario) -> float:
    """Variant 2: Simple weighted average baseline (no DS theory)."""
    ontology = FusionEngine().ontology
    profile = ontology.get_profile(scenario.tsr_class_id)
    modifier = profile.base_risk_modifier if profile else 0
    return 0.65 * scenario.dz_score + 0.35 * (modifier * 100)


def fusion_ds_full(scenario: Scenario) -> float:
    """Variant 3: Full DS Fusion (the complete system)."""
    engine = FusionEngine()
    dz = DZInput(
        risk_score=scenario.dz_score,
        risk_level=_level(scenario.dz_score),
        confidence=scenario.dz_confidence,
        risk_probability=scenario.dz_score / 100.0,
        weather_condition=scenario.weather,
        road_surface=scenario.road_surface,
        speed_kph=scenario.speed_kph
    )
    tsr = TSRInput(
        class_id=scenario.tsr_class_id,
        class_name=scenario.tsr_class_name,
        confidence=scenario.tsr_confidence,
        is_confident=True
    )
    return engine.fuse(dz_input=dz, tsr_input=tsr).fused_risk_score


def fusion_murphy(scenario: Scenario) -> float:
    """Variant 4: Murphy's Rule instead of Dempster's Rule."""
    ontology = FusionEngine().ontology
    profile = ontology.get_profile(scenario.tsr_class_id)
    modifier = profile.base_risk_modifier if profile else 0
    
    # Build mass functions manually
    dz_mass = EvidenceConstructor.from_dz(
        scenario.dz_score / 100.0, scenario.dz_confidence
    )
    tsr_mass = EvidenceConstructor.from_tsr(
        modifier, scenario.tsr_confidence
    )
    
    combined, _ = murphy_combine([dz_mass, tsr_mass])
    return combined.pignistic_probability * 100


def fusion_ds_no_temporal_buffer(scenario: Scenario) -> float:
    """Variant 5: DS without temporal buffer (single-frame evidence only)."""
    ontology = FusionEngine().ontology
    profile = ontology.get_profile(scenario.tsr_class_id)
    modifier = profile.base_risk_modifier if profile else 0
    
    # Build raw mass functions and combine directly (no buffer aggregation)
    dz_mass = EvidenceConstructor.from_dz(
        scenario.dz_score / 100.0, scenario.dz_confidence
    )
    tsr_mass = EvidenceConstructor.from_tsr(
        modifier, scenario.tsr_confidence, temporal_decay=1.0  # No decay
    )
    
    combined, _ = dempster_combine(dz_mass, tsr_mass)
    return combined.pignistic_probability * 100


def fusion_ds_no_adaptive_weights(scenario: Scenario) -> float:
    """Variant 6: DS without adaptive weights (equal weighting)."""
    ontology = FusionEngine().ontology
    profile = ontology.get_profile(scenario.tsr_class_id)
    modifier = profile.base_risk_modifier if profile else 0
    
    # Use equal weighting — no adaptive modulation
    dz_mass = EvidenceConstructor.from_dz(
        scenario.dz_score / 100.0, scenario.dz_confidence
    )
    # No reliability discount (equal trust)
    tsr_mass = EvidenceConstructor.from_tsr(
        modifier, scenario.tsr_confidence,
        temporal_decay=1.0, reliability_discount=1.0
    )
    
    combined, _ = dempster_combine(dz_mass, tsr_mass)
    return combined.pignistic_probability * 100


def fusion_ds_no_contextual_rules(scenario: Scenario) -> float:
    """Variant 7: DS without contextual rules (base modifier only, no weather/speed)."""
    ontology = FusionEngine().ontology
    profile = ontology.get_profile(scenario.tsr_class_id)
    
    # Use raw base_risk_modifier — no contextual adjustments
    raw_modifier = profile.base_risk_modifier if profile else 0
    
    dz_mass = EvidenceConstructor.from_dz(
        scenario.dz_score / 100.0, scenario.dz_confidence
    )
    tsr_mass = EvidenceConstructor.from_tsr(
        raw_modifier, scenario.tsr_confidence,
        temporal_decay=1.0, reliability_discount=1.0
    )
    
    combined, _ = dempster_combine(dz_mass, tsr_mass)
    return combined.pignistic_probability * 100


# ─── Main Ablation Runner ────────────────────────────────────────────

METHODS = {
    "DZ-Only":                fusion_dz_only,
    "Weighted Avg":           fusion_weighted_average,
    "DS Fusion (full)":       fusion_ds_full,
    "Murphy's Rule":          fusion_murphy,
    "DS (no temp buffer)":    fusion_ds_no_temporal_buffer,
    "DS (no adaptive wt)":    fusion_ds_no_adaptive_weights,
    "DS (no context rules)":  fusion_ds_no_contextual_rules,
}


def run_ablation():
    """Run expanded ablation study comparing all fusion variants."""
    
    print("=" * 100)
    print("EXPANDED ABLATION STUDY: Fusion Method & Component Comparison")
    print("=" * 100)
    
    all_results: Dict[str, List[float]] = {name: [] for name in METHODS}
    scenario_details = []
    
    for scenario in SCENARIOS:
        print(f"\n{'─' * 80}")
        print(f"Scenario: {scenario.name}")
        print(f"  {scenario.description}")
        print(f"  DZ: {scenario.dz_score} (conf={scenario.dz_confidence:.0%}), "
              f"TSR: {scenario.tsr_class_name} (conf={scenario.tsr_confidence:.0%})")
        
        dz_only_score = None
        row = {"scenario": scenario.name, "expected": scenario.expected_direction}
        
        print(f"\n  {'Method':<25} {'Score':>7} {'Δ from DZ':>10} {'Dir':>5}")
        print(f"  {'─' * 50}")
        
        for method_name, method_fn in METHODS.items():
            score = method_fn(scenario)
            all_results[method_name].append(score)
            row[method_name] = round(score, 1)
            
            if method_name == "DZ-Only":
                dz_only_score = score
                delta_str = "—"
                dir_str = "—"
            else:
                delta = score - dz_only_score
                correctness = compute_directional_correctness(delta, scenario.expected_direction)
                delta_str = f"{delta:+.1f}"
                dir_str = correctness
            
            print(f"  {method_name:<25} {score:>7.1f} {delta_str:>10} {dir_str:>5}")
        
        scenario_details.append(row)
    
    # ── Summary Statistics ──
    print(f"\n{'=' * 100}")
    print("SUMMARY STATISTICS ACROSS ALL SCENARIOS")
    print(f"{'=' * 100}")
    
    print(f"\n{'Method':<25} {'Mean':>8} {'Std':>8} {'Min':>8} {'Max':>8} {'Correct':>9}")
    print("─" * 68)
    
    for method_name, scores in all_results.items():
        mean = statistics.mean(scores)
        std = statistics.stdev(scores) if len(scores) > 1 else 0
        mn = min(scores)
        mx = max(scores)
        
        # Directional correctness
        if method_name == "DZ-Only":
            correct = "—"
        else:
            correct_count = 0
            for i, scenario in enumerate(SCENARIOS):
                delta = scores[i] - all_results["DZ-Only"][i]
                c = compute_directional_correctness(delta, scenario.expected_direction)
                if c == "✓":
                    correct_count += 1
            correct = f"{correct_count}/{len(SCENARIOS)}"
        
        print(f"{method_name:<25} {mean:>8.1f} {std:>8.1f} {mn:>8.1f} {mx:>8.1f} {correct:>9}")
    
    # ── Pairwise Comparison: DS vs Murphy ──
    print(f"\n{'=' * 100}")
    print("DS FUSION vs MURPHY'S RULE: Head-to-Head Comparison")
    print(f"{'=' * 100}")
    
    ds_scores = all_results["DS Fusion (full)"]
    mu_scores = all_results["Murphy's Rule"]
    
    print(f"\n{'Scenario':<30} {'DS':>7} {'Murphy':>8} {'Diff':>7}")
    print("─" * 55)
    
    for i, scenario in enumerate(SCENARIOS):
        diff = ds_scores[i] - mu_scores[i]
        print(f"{scenario.name:<30} {ds_scores[i]:>7.1f} {mu_scores[i]:>8.1f} {diff:>+7.1f}")
    
    ds_mean = statistics.mean(ds_scores)
    mu_mean = statistics.mean(mu_scores)
    diff_mean = ds_mean - mu_mean
    print("─" * 55)
    print(f"{'MEAN':<30} {ds_mean:>7.1f} {mu_mean:>8.1f} {diff_mean:>+7.1f}")
    
    # ── Component Contribution ──
    print(f"\n{'=' * 100}")
    print("COMPONENT CONTRIBUTION ANALYSIS")
    print("(Delta vs DS without each component — positive = component increases the score)")
    print(f"{'=' * 100}")
    
    components = [
        ("Temporal Buffer",   "DS (no temp buffer)"),
        ("Adaptive Weights",  "DS (no adaptive wt)"),
        ("Contextual Rules",  "DS (no context rules)"),
    ]
    
    print(f"\n{'Scenario':<30}", end="")
    for comp_name, _ in components:
        print(f" {comp_name:>16}", end="")
    print()
    print("─" * 78)
    
    for i, scenario in enumerate(SCENARIOS):
        print(f"{scenario.name:<30}", end="")
        for _, ablated_key in components:
            delta = ds_scores[i] - all_results[ablated_key][i]
            print(f" {delta:>+16.1f}", end="")
        print()
    
    # Mean contributions
    print("─" * 78)
    print(f"{'MEAN CONTRIBUTION':<30}", end="")
    for _, ablated_key in components:
        deltas = [ds_scores[i] - all_results[ablated_key][i] for i in range(len(SCENARIOS))]
        mean_delta = statistics.mean(deltas)
        print(f" {mean_delta:>+16.1f}", end="")
    print()
    
    # Save full results
    output = {
        "scenarios": [s.name for s in SCENARIOS],
        "results": {k: [round(v, 2) for v in vs] for k, vs in all_results.items()},
        "scenario_details": scenario_details,
    }
    
    with open("evaluation/ablation_results.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\nResults saved to evaluation/ablation_results.json")


if __name__ == "__main__":
    run_ablation()
