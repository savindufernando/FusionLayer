"""
Conflict Analysis — Research Evaluation Script
Analyzes when and why TSR and DZ modules disagree, and how DS theory resolves conflicts.

Run: python -m evaluation.conflict_analysis
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
from typing import List, Dict
from src.fusion_engine import FusionEngine, TSRInput, DZInput
from src.evidence import EvidenceConstructor, dempster_combine


def analyze_conflicts():
    """
    Generate and analyze conflict patterns between TSR and DZ modules.
    
    Tests systematic scenarios where the modules are expected to disagree:
    - Safe zone but hazard sign detected
    - High risk zone but informational sign detected
    - Varying confidence levels affecting conflict magnitude
    """
    
    print("=" * 80)
    print("CONFLICT ANALYSIS: TSR vs DZ Module Disagreement")
    print("=" * 80)
    
    engine = FusionEngine()
    conflict_data = []
    
    # Generate conflict scenarios
    scenarios = [
        # (name, dz_score, dz_conf, tsr_class_id, tsr_name, tsr_conf, description)
        ("Safe + Accident Sign", 10, 0.90, 83, "accident", 0.95,
         "DZ says very safe but TSR detects accident sign"),
        ("Safe + Curve Sign", 15, 0.85, 87, "curve_to_left", 0.90,
         "DZ says safe but TSR detects curve ahead"),
        ("High + Parking Sign", 80, 0.90, 13, "parking", 0.95,
         "DZ says dangerous but TSR detects parking (safe area)"),
        ("High + Motorway Info", 75, 0.88, 2, "motorway", 0.92,
         "DZ says dangerous but TSR detects motorway info"),
        ("Medium + Stop Sign", 50, 0.85, 39, "stop", 0.90,
         "Both indicate moderate-high risk — should agree"),
        ("Low + Low-conf Hazard", 20, 0.90, 83, "accident", 0.55,
         "Low DZ risk, low-confidence hazard sign"),
        ("High + High-conf Safe Sign", 85, 0.95, 13, "parking", 0.98,
         "Maximum disagreement scenario"),
    ]
    
    for name, dz_score, dz_conf, tsr_id, tsr_name, tsr_conf, desc in scenarios:
        engine.reset()
        
        dz = DZInput(
            risk_score=dz_score,
            risk_level="HIGH" if dz_score >= 65 else ("MEDIUM" if dz_score >= 35 else "LOW"),
            confidence=dz_conf,
            risk_probability=dz_score / 100.0
        )
        tsr = TSRInput(
            class_id=tsr_id,
            class_name=tsr_name,
            confidence=tsr_conf,
            is_confident=tsr_conf >= 0.5
        )
        
        result = engine.fuse(dz_input=dz, tsr_input=tsr)
        
        entry = {
            "scenario": name,
            "description": desc,
            "dz_score": dz_score,
            "dz_level": dz.risk_level,
            "tsr_sign": tsr_name,
            "tsr_confidence": tsr_conf,
            "fused_score": result.fused_risk_score,
            "fused_level": result.fused_risk_level,
            "conflict_K": result.conflict_measure,
            "belief_D": result.belief_dangerous,
            "plausibility_D": result.plausibility_dangerous,
            "uncertainty": result.uncertainty_width
        }
        conflict_data.append(entry)
        
        conflict_level = "HIGH" if result.conflict_measure > 0.3 else \
                         ("MEDIUM" if result.conflict_measure > 0.1 else "LOW")
        
        print(f"\n{'─' * 60}")
        print(f"Scenario: {name}")
        print(f"  {desc}")
        print(f"  DZ: {dz_score:.0f} ({dz.risk_level}) | TSR: {tsr_name} (conf: {tsr_conf:.0%})")
        print(f"  Fused: {result.fused_risk_score:.1f} ({result.fused_risk_level})")
        print(f"  Conflict K: {result.conflict_measure:.4f} [{conflict_level}]")
        print(f"  Bel(D)={result.belief_dangerous:.3f}  "
              f"Pl(D)={result.plausibility_dangerous:.3f}  "
              f"Uncertainty={result.uncertainty_width:.3f}")
    
    # Confidence sweep: how does TSR confidence affect conflict?
    print(f"\n{'=' * 80}")
    print("CONFIDENCE SWEEP: TSR Confidence vs Conflict Measure")
    print("(Fixed: DZ=15/LOW/0.90, TSR=accident)")
    print(f"{'=' * 80}")
    print(f"{'TSR Conf':>10} {'Conflict K':>12} {'Fused Score':>13} {'Level':>8}")
    
    for tsr_conf_pct in range(40, 100, 5):
        tsr_conf = tsr_conf_pct / 100.0
        engine.reset()
        
        dz = DZInput(risk_score=15, risk_level="LOW",
                     confidence=0.90, risk_probability=0.15)
        tsr = TSRInput(class_id=83, class_name="accident",
                       confidence=tsr_conf, is_confident=tsr_conf >= 0.5)
        
        result = engine.fuse(dz_input=dz, tsr_input=tsr)
        print(f"{tsr_conf:>10.0%} {result.conflict_measure:>12.4f} "
              f"{result.fused_risk_score:>13.1f} {result.fused_risk_level:>8}")
    
    # Save results
    with open("evaluation/conflict_results.json", "w") as f:
        json.dump(conflict_data, f, indent=2)
    
    print(f"\nResults saved to evaluation/conflict_results.json")


if __name__ == "__main__":
    analyze_conflicts()
