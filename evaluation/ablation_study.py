"""
Ablation Study — Research Evaluation Script
Compares fusion methods: DZ-only, TSR-only, Weighted Average, DS Fusion.

Run: python -m evaluation.ablation_study
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from typing import List, Dict, Tuple
from dataclasses import dataclass
from src.fusion_engine import FusionEngine, TSRInput, DZInput, HotspotInput
from src.evidence import MassFunction, EvidenceConstructor, dempster_combine


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


def run_ablation():
    """Run ablation comparing fusion methods."""
    
    print("=" * 80)
    print("ABLATION STUDY: Fusion Method Comparison")
    print("=" * 80)
    
    results = {"dz_only": [], "weighted_avg": [], "ds_fusion": []}
    
    for scenario in SCENARIOS:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {scenario.name}")
        print(f"  {scenario.description}")
        print(f"  DZ: {scenario.dz_score}, TSR: {scenario.tsr_class_name} "
              f"(conf: {scenario.tsr_confidence:.0%})")
        
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
        
        # 1. DZ-only (no fusion)
        engine_dz = FusionEngine()
        dz_result = engine_dz.fuse(dz_input=dz)
        dz_score = dz_result.fused_risk_score
        
        # 2. DS Fusion
        engine_ds = FusionEngine()
        ds_result = engine_ds.fuse(dz_input=dz, tsr_input=tsr)
        ds_score = ds_result.fused_risk_score
        
        # 3. Simple Weighted Average (baseline)
        ontology = engine_ds.ontology
        profile = ontology.get_profile(scenario.tsr_class_id)
        modifier = profile.base_risk_modifier if profile else 0
        wa_score = 0.65 * scenario.dz_score + 0.35 * (modifier * 100)
        
        results["dz_only"].append(dz_score)
        results["weighted_avg"].append(wa_score)
        results["ds_fusion"].append(ds_score)
        
        delta = ds_score - dz_score
        direction = "UP" if delta > 2 else ("DOWN" if delta < -2 else "~=")
        correctness = "OK" if (
            (scenario.expected_direction == "increase" and delta > 0) or
            (scenario.expected_direction == "decrease" and delta < 0) or
            (scenario.expected_direction == "maintain" and abs(delta) < 10)
        ) else "FAIL"
        
        print(f"  Results:")
        print(f"    DZ-Only:     {dz_score:6.1f}")
        print(f"    Weighted Avg:{wa_score:6.1f}")
        print(f"    DS Fusion:   {ds_score:6.1f}  {direction} ({delta:+.1f}) {correctness}")
        print(f"    DS Details:  Bel={ds_result.belief_dangerous:.3f} "
              f"Pl={ds_result.plausibility_dangerous:.3f} K={ds_result.conflict_measure:.3f}")
    
    # Summary statistics
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print(f"{'Method':<20} {'Mean Score':>12} {'Std Dev':>10}")
    print(f"{'─' * 42}")
    
    for method, scores in results.items():
        import statistics
        mean = statistics.mean(scores)
        std = statistics.stdev(scores) if len(scores) > 1 else 0
        print(f"{method:<20} {mean:12.1f} {std:10.1f}")
    
    # Save results
    with open("evaluation/ablation_results.json", "w") as f:
        json.dump({
            "scenarios": [s.name for s in SCENARIOS],
            "results": results
        }, f, indent=2)
    
    print(f"\nResults saved to evaluation/ablation_results.json")


def _level(score: float) -> str:
    if score >= 65: return "HIGH"
    if score >= 35: return "MEDIUM"
    return "LOW"


if __name__ == "__main__":
    run_ablation()
