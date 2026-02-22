"""
Counterfactual Explanation Analysis — Research Evaluation Script

Runs source-ablation experiments to generate counterfactual explanations:
- "Removing TSR changed the risk from X → Y"
- "Removing hotspot data changed the risk from X → Y"

This demonstrates the causal contribution of each evidence source to the
final fused risk assessment, providing XAI (Explainable AI) at the fusion level.

References:
    Miller, T. (2019). Explanation in Artificial Intelligence: Insights from
    the Social Sciences. Artificial Intelligence, 267, 1-38.
    
    Wachter, S. et al. (2017). Counterfactual Explanations without Opening
    the Black Box. Harvard Journal of Law & Technology, 31(2).

Run: python -m evaluation.counterfactual_analysis
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

from src.fusion_engine import FusionEngine, TSRInput, DZInput, HotspotInput, FusionResult


# ─── Scenarios ────────────────────────────────────────────────────────

@dataclass
class CounterfactualScenario:
    """A scenario for counterfactual analysis."""
    name: str
    description: str
    dz_score: float
    dz_confidence: float
    tsr_class_id: int
    tsr_class_name: str
    tsr_confidence: float
    hotspot_boost: float
    hotspot_count: int
    weather: str
    road_surface: str
    speed_kph: float


SCENARIOS: List[CounterfactualScenario] = [
    CounterfactualScenario(
        "Curve + Rain + Hotspot",
        "Dangerous curve on wet road near known accident hotspot",
        42, 0.88, 87, "curve_to_left", 0.94,
        0.3, 6, "Rain", "Wet", 55
    ),
    CounterfactualScenario(
        "Accident Sign + High DZ",
        "Accident warning sign in a high-risk zone",
        75, 0.92, 83, "accident", 0.95,
        0.0, 0, "Fine", "Dry", 60
    ),
    CounterfactualScenario(
        "School Zone + Hotspot",
        "School zone speed limit near accident hotspot",
        45, 0.85, 68,
        "maximum_speed_limit_(all_vehicles_within_school_areas_and_hospitals)",
        0.88, 0.25, 4, "Fine", "Dry", 35
    ),
    CounterfactualScenario(
        "Slippery Road + Rain",
        "Slippery road sign during rainstorm",
        50, 0.86, 112, "slippery_road", 0.90,
        0.0, 0, "Rain", "Wet", 50
    ),
    CounterfactualScenario(
        "Night Level Crossing",
        "Unprotected level crossing at night",
        55, 0.84, 102, "level_crossing_without_barriers_ahead", 0.87,
        0.15, 3, "Dark", "Dry", 45
    ),
    CounterfactualScenario(
        "Safe Road + Parking",
        "Informational parking sign on safe road (low impact expected)",
        15, 0.90, 13, "parking", 0.95,
        0.0, 0, "Fine", "Dry", 30
    ),
    CounterfactualScenario(
        "Stop Sign + Medium Risk",
        "Stop sign at intersection with moderate zone risk",
        40, 0.87, 39, "stop", 0.91,
        0.2, 5, "Fine", "Dry", 40
    ),
    CounterfactualScenario(
        "Motorway + High Speed",
        "Motorway info sign at high speed (minimal sign impact expected)",
        30, 0.90, 2, "motorway", 0.96,
        0.0, 0, "Fine", "Dry", 80
    ),
]


# ─── Explanation Generator ────────────────────────────────────────────

def _level(score: float) -> str:
    if score >= 65: return "HIGH"
    if score >= 35: return "MEDIUM"
    return "LOW"


def generate_explanation(
    scenario_name: str,
    full_score: float,
    full_level: str,
    no_tsr_score: float,
    no_tsr_level: str,
    no_hotspot_score: float,
    no_hotspot_level: str,
    tsr_sign: str,
    has_hotspot: bool
) -> str:
    """
    Generate a natural language counterfactual explanation.
    
    Returns:
        Human-readable explanation string.
    """
    parts = [f"Fused risk: {full_score:.1f}/100 ({full_level})"]
    
    # TSR counterfactual
    tsr_delta = full_score - no_tsr_score
    if abs(tsr_delta) > 1.0:
        direction = "increased" if tsr_delta > 0 else "decreased"
        parts.append(
            f"• The '{tsr_sign}' sign detection {direction} risk by "
            f"{abs(tsr_delta):.1f} points ({no_tsr_score:.1f} → {full_score:.1f})"
        )
        if no_tsr_level != full_level:
            parts.append(
                f"  → Without TSR, risk level would be {no_tsr_level} instead of {full_level}"
            )
    else:
        parts.append(f"• The '{tsr_sign}' sign had minimal impact (Δ={tsr_delta:+.1f})")
    
    # Hotspot counterfactual
    if has_hotspot:
        hotspot_delta = full_score - no_hotspot_score
        if abs(hotspot_delta) > 1.0:
            direction = "increased" if hotspot_delta > 0 else "decreased"
            parts.append(
                f"• Accident hotspot data {direction} risk by "
                f"{abs(hotspot_delta):.1f} points ({no_hotspot_score:.1f} → {full_score:.1f})"
            )
        else:
            parts.append(f"• Hotspot data had minimal impact (Δ={hotspot_delta:+.1f})")
    
    return "\n".join(parts)


# ─── Main Analysis ────────────────────────────────────────────────────

def run_counterfactual_analysis():
    """Run counterfactual source-ablation analysis."""
    
    print("=" * 85)
    print("COUNTERFACTUAL EXPLANATION ANALYSIS")
    print("Source Ablation: What happens when we remove each evidence source?")
    print("=" * 85)
    
    all_results = []
    
    for scenario in SCENARIOS:
        print(f"\n{'─' * 70}")
        print(f"Scenario: {scenario.name}")
        print(f"  {scenario.description}")
        
        # Build inputs
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
        
        hotspot = None
        has_hotspot = scenario.hotspot_boost > 0 and scenario.hotspot_count > 0
        if has_hotspot:
            hotspot = HotspotInput(
                risk_boost=scenario.hotspot_boost,
                report_count=scenario.hotspot_count
            )
        
        # ── Run 1: Full fusion (all sources) ──
        engine_full = FusionEngine()
        full_result = engine_full.fuse(dz_input=dz, tsr_input=tsr, hotspot_input=hotspot)
        
        # ── Run 2: Without TSR (DZ + hotspot only) ──
        engine_no_tsr = FusionEngine()
        no_tsr_result = engine_no_tsr.fuse(dz_input=dz, hotspot_input=hotspot)
        
        # ── Run 3: Without hotspot (DZ + TSR only) ──
        engine_no_hotspot = FusionEngine()
        no_hotspot_result = engine_no_hotspot.fuse(dz_input=dz, tsr_input=tsr)
        
        # ── Run 4: DZ only (no TSR, no hotspot) ──
        engine_dz_only = FusionEngine()
        dz_only_result = engine_dz_only.fuse(dz_input=dz)
        
        # Compute deltas
        tsr_delta = full_result.fused_risk_score - no_tsr_result.fused_risk_score
        hotspot_delta = full_result.fused_risk_score - no_hotspot_result.fused_risk_score if has_hotspot else 0
        tsr_from_baseline_delta = no_tsr_result.fused_risk_score - dz_only_result.fused_risk_score
        
        # Store result
        entry = {
            "scenario": scenario.name,
            "description": scenario.description,
            "full_fusion": {
                "score": round(full_result.fused_risk_score, 1),
                "level": full_result.fused_risk_level,
                "conflict": round(full_result.conflict_measure, 4),
            },
            "without_tsr": {
                "score": round(no_tsr_result.fused_risk_score, 1),
                "level": no_tsr_result.fused_risk_level,
                "delta": round(tsr_delta, 1),
            },
            "without_hotspot": {
                "score": round(no_hotspot_result.fused_risk_score, 1),
                "level": no_hotspot_result.fused_risk_level,
                "delta": round(hotspot_delta, 1),
            } if has_hotspot else None,
            "dz_only": {
                "score": round(dz_only_result.fused_risk_score, 1),
                "level": dz_only_result.fused_risk_level,
            },
        }
        all_results.append(entry)
        
        # Print comparison table
        print(f"\n  {'Configuration':<25} {'Score':>7} {'Level':>7} {'Δ from Full':>12}")
        print(f"  {'─' * 53}")
        print(f"  {'Full Fusion':<25} {full_result.fused_risk_score:>7.1f} "
              f"{full_result.fused_risk_level:>7} {'—':>12}")
        print(f"  {'Without TSR':<25} {no_tsr_result.fused_risk_score:>7.1f} "
              f"{no_tsr_result.fused_risk_level:>7} {-tsr_delta:>+12.1f}")
        if has_hotspot:
            print(f"  {'Without Hotspot':<25} {no_hotspot_result.fused_risk_score:>7.1f} "
                  f"{no_hotspot_result.fused_risk_level:>7} {-hotspot_delta:>+12.1f}")
        print(f"  {'DZ Only (baseline)':<25} {dz_only_result.fused_risk_score:>7.1f} "
              f"{dz_only_result.fused_risk_level:>7} "
              f"{dz_only_result.fused_risk_score - full_result.fused_risk_score:>+12.1f}")
        
        # Natural language explanation
        explanation = generate_explanation(
            scenario.name,
            full_result.fused_risk_score, full_result.fused_risk_level,
            no_tsr_result.fused_risk_score, no_tsr_result.fused_risk_level,
            no_hotspot_result.fused_risk_score if has_hotspot else full_result.fused_risk_score,
            no_hotspot_result.fused_risk_level if has_hotspot else full_result.fused_risk_level,
            scenario.tsr_class_name,
            has_hotspot
        )
        print(f"\n  Explanation:")
        for line in explanation.split("\n"):
            print(f"    {line}")
    
    # ── Summary Table ──
    print(f"\n{'=' * 85}")
    print("COUNTERFACTUAL IMPACT SUMMARY")
    print(f"{'=' * 85}")
    
    print(f"\n{'Scenario':<30} {'TSR Impact':>11} {'Hotspot Impact':>15} {'Full':>6} {'DZ-Only':>8}")
    print("─" * 72)
    
    for r in all_results:
        tsr_imp = r["without_tsr"]["delta"]
        hot_imp = r["without_hotspot"]["delta"] if r["without_hotspot"] else 0
        print(f"{r['scenario']:<30} {tsr_imp:>+11.1f} {hot_imp:>+15.1f} "
              f"{r['full_fusion']['score']:>6.1f} {r['dz_only']['score']:>8.1f}")
    
    # Average impacts
    tsr_impacts = [r["without_tsr"]["delta"] for r in all_results]
    hotspot_impacts = [r["without_hotspot"]["delta"] for r in all_results if r["without_hotspot"]]
    
    print("─" * 72)
    avg_tsr = sum(tsr_impacts) / len(tsr_impacts) if tsr_impacts else 0
    avg_hot = sum(hotspot_impacts) / len(hotspot_impacts) if hotspot_impacts else 0
    print(f"{'AVERAGE IMPACT':<30} {avg_tsr:>+11.1f} {avg_hot:>+15.1f}")
    
    # Key findings
    max_tsr_idx = max(range(len(tsr_impacts)), key=lambda i: abs(tsr_impacts[i]))
    print(f"\n  → Highest TSR impact: {all_results[max_tsr_idx]['scenario']} "
          f"(Δ={tsr_impacts[max_tsr_idx]:+.1f})")
    
    if hotspot_impacts:
        max_hot_idx = max(range(len(hotspot_impacts)), key=lambda i: abs(hotspot_impacts[i]))
        hot_scenarios = [r for r in all_results if r["without_hotspot"]]
        print(f"  → Highest Hotspot impact: {hot_scenarios[max_hot_idx]['scenario']} "
              f"(Δ={hotspot_impacts[max_hot_idx]:+.1f})")
    
    # Level changes
    level_changes = sum(1 for r in all_results
                        if r["without_tsr"]["level"] != r["full_fusion"]["level"])
    print(f"  → TSR caused level change in {level_changes}/{len(all_results)} scenarios")
    
    # Save results
    with open("evaluation/counterfactual_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\nResults saved to evaluation/counterfactual_results.json")


if __name__ == "__main__":
    run_counterfactual_analysis()
