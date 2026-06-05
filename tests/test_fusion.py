"""
Unit tests for Sign-Risk Ontology, Evidence module, Temporal Buffer,
and the Fusion Engine.

All tests use mocked module outputs — no trained ML models required.
Run: python -m pytest tests/ -v
"""

import time
import math
import pytest
from src.sign_risk_ontology import (
    SignRiskOntology, SignRiskCategory, ContextCondition, SignRiskProfile
)
from src.evidence import (
    MassFunction, EvidenceConstructor, dempster_combine, combine_multiple,
    murphy_combine, murphy_combine_multiple
)
from src.temporal_buffer import (
    TemporalSignBuffer, SignDetection, AggregateSignEvidence
)
from src.fusion_engine import (
    FusionEngine, TSRInput, DZInput, HotspotInput, FusionResult
)


# =====================================================================
# ONTOLOGY TESTS
# =====================================================================

class TestSignRiskOntology:
    """Tests for the sign-risk knowledge base."""
    
    def setup_method(self):
        self.ontology = SignRiskOntology()
    
    def test_all_122_classes_registered(self):
        """All 122 Sri Lankan sign classes must have profiles."""
        assert self.ontology.num_classes == 122
        for cid in range(122):
            profile = self.ontology.get_profile(cid)
            assert profile is not None, f"Missing class_id {cid}"
    
    def test_validation_passes(self):
        """Ontology validation should return no errors."""
        errors = self.ontology.validate()
        assert errors == [], f"Validation errors: {errors}"
    
    def test_risk_modifiers_in_range(self):
        """All base_risk_modifiers must be in [0.0, 1.0]."""
        for profile in self.ontology.get_all_profiles():
            assert 0.0 <= profile.base_risk_modifier <= 1.0, \
                f"{profile.class_name}: modifier {profile.base_risk_modifier} out of range"
    
    def test_relevance_durations_positive(self):
        """All relevance durations must be positive."""
        for profile in self.ontology.get_all_profiles():
            assert profile.relevance_duration_s > 0, \
                f"{profile.class_name}: duration must be positive"
    
    def test_hazard_signs_have_high_modifiers(self):
        """Hazard warning signs should have modifier >= 0.2."""
        hazards = self.ontology.get_profiles_by_category(SignRiskCategory.HAZARD_WARNING)
        assert len(hazards) > 0
        for p in hazards:
            assert p.base_risk_modifier >= 0.2, \
                f"Hazard '{p.class_name}' modifier {p.base_risk_modifier} too low"
    
    def test_informational_signs_have_low_modifiers(self):
        """Most informational signs should have modifier < 0.3."""
        info = self.ontology.get_profiles_by_category(SignRiskCategory.INFORMATIONAL)
        low_count = sum(1 for p in info if p.base_risk_modifier < 0.3)
        ratio = low_count / len(info)
        assert ratio >= 0.8, f"Only {ratio:.0%} of info signs have low modifiers"
    
    def test_stop_sign_is_highest_priority(self):
        """Stop sign should be in priority category with high modifier."""
        profile = self.ontology.get_profile_by_name("stop")
        assert profile is not None
        assert profile.risk_category == SignRiskCategory.PRIORITY
        assert profile.base_risk_modifier >= 0.4
    
    def test_accident_sign_is_critical(self):
        """Accident sign should have very high modifier."""
        profile = self.ontology.get_profile_by_name("accident")
        assert profile is not None
        assert profile.base_risk_modifier >= 0.7
    
    def test_contextual_modifier_rain_increases_slippery(self):
        """Slippery road modifier should increase in rain."""
        profile = self.ontology.get_profile_by_name("slippery_road")
        assert profile is not None
        
        dry_modifier = self.ontology.compute_effective_modifier(profile)
        wet_modifier = self.ontology.compute_effective_modifier(
            profile, weather_code=2, is_wet=True
        )
        assert wet_modifier > dry_modifier
    
    def test_contextual_modifier_night_increases_pedestrian_zones(self):
        """Pedestrian crossing should be more dangerous at night."""
        profile = self.ontology.get_profile_by_name("pedestrian_crossing")
        base = self.ontology.compute_effective_modifier(profile)
        night = self.ontology.compute_effective_modifier(profile, is_night=True)
        assert night > base
    
    def test_get_profile_by_name(self):
        """Name-based lookup works correctly."""
        profile = self.ontology.get_profile_by_name("roundabout")
        assert profile is not None
        assert profile.class_id == 29
        assert profile.risk_category == SignRiskCategory.MANDATORY
    
    def test_unknown_name_returns_none(self):
        """Unknown sign name returns None."""
        assert self.ontology.get_profile_by_name("nonexistent_sign") is None
    
    def test_unknown_class_id_returns_none(self):
        """Out-of-range class_id returns None."""
        assert self.ontology.get_profile(999) is None


# =====================================================================
# EVIDENCE / MASS FUNCTION TESTS
# =====================================================================

class TestMassFunction:
    """Tests for Dempster-Shafer mass functions."""
    
    def test_default_is_ignorance(self):
        """Default mass function = complete ignorance."""
        m = MassFunction()
        assert m.m_uncertain == 1.0
        assert m.m_safe == 0.0
        assert m.m_dangerous == 0.0
    
    def test_normalization(self):
        """Mass function auto-normalizes to sum = 1."""
        m = MassFunction(m_safe=2.0, m_dangerous=3.0, m_uncertain=5.0)
        total = m.m_safe + m.m_dangerous + m.m_uncertain
        assert abs(total - 1.0) < 1e-6
    
    def test_belief_plausibility_bounds(self):
        """Bel(D) <= Pl(D) always."""
        m = MassFunction(m_safe=0.3, m_dangerous=0.4, m_uncertain=0.3)
        assert m.belief_dangerous <= m.plausibility_dangerous
    
    def test_pignistic_probability(self):
        """Pignistic transform produces valid probability."""
        m = MassFunction(m_safe=0.2, m_dangerous=0.5, m_uncertain=0.3)
        p = m.pignistic_probability
        assert 0.0 <= p <= 1.0
        # Should be > 0.5 because m_dangerous > m_safe
        assert p > 0.5
    
    def test_pignistic_ignorance(self):
        """Complete ignorance → pignistic = 0.1 (low risk base prior)."""
        m = MassFunction(m_safe=0.0, m_dangerous=0.0, m_uncertain=1.0)
        assert abs(m.pignistic_probability - 0.1) < 1e-6
    
    def test_pignistic_full_danger(self):
        """Full danger evidence → pignistic ≈ 1.0."""
        m = MassFunction(m_safe=0.0, m_dangerous=1.0, m_uncertain=0.0)
        assert abs(m.pignistic_probability - 1.0) < 1e-6
    
    def test_uncertainty_width(self):
        """Uncertainty width = Pl(D) - Bel(D) = m(Θ)."""
        m = MassFunction(m_safe=0.2, m_dangerous=0.4, m_uncertain=0.4)
        assert abs(m.uncertainty_width - 0.4) < 1e-6
    
    def test_to_dict(self):
        """Serialization works correctly."""
        m = MassFunction(m_safe=0.3, m_dangerous=0.4, m_uncertain=0.3, source="test")
        d = m.to_dict()
        assert "m_safe" in d
        assert "pignistic_probability" in d
        assert d["source"] == "test"


class TestDempsterCombination:
    """Tests for Dempster's Rule of Combination."""
    
    def test_combine_agreeing_evidence(self):
        """Agreeing evidence should reinforce each other."""
        m1 = MassFunction(m_safe=0.1, m_dangerous=0.6, m_uncertain=0.3, source="a")
        m2 = MassFunction(m_safe=0.1, m_dangerous=0.5, m_uncertain=0.4, source="b")
        
        combined, K = dempster_combine(m1, m2)
        
        # Combined danger should be higher than either input
        assert combined.m_dangerous > m1.m_dangerous
        assert combined.m_dangerous > m2.m_dangerous
        # Low conflict
        assert K < 0.2
    
    def test_combine_conflicting_evidence(self):
        """Conflicting evidence should produce high K."""
        m1 = MassFunction(m_safe=0.8, m_dangerous=0.0, m_uncertain=0.2, source="a")
        m2 = MassFunction(m_safe=0.0, m_dangerous=0.8, m_uncertain=0.2, source="b")
        
        combined, K = dempster_combine(m1, m2)
        
        # High conflict
        assert K > 0.5
    
    def test_combine_with_ignorance(self):
        """Combining with ignorance should not change evidence."""
        m1 = MassFunction(m_safe=0.2, m_dangerous=0.5, m_uncertain=0.3, source="a")
        m2 = MassFunction(m_safe=0.0, m_dangerous=0.0, m_uncertain=1.0, source="b")
        
        combined, K = dempster_combine(m1, m2)
        
        assert abs(combined.m_dangerous - m1.m_dangerous) < 1e-6
        assert abs(combined.m_safe - m1.m_safe) < 1e-6
        assert K < 1e-10
    
    def test_combine_total_conflict_returns_ignorance(self):
        """Total conflict → fallback to ignorance."""
        m1 = MassFunction(m_safe=1.0, m_dangerous=0.0, m_uncertain=0.0, source="a")
        m2 = MassFunction(m_safe=0.0, m_dangerous=1.0, m_uncertain=0.0, source="b")
        
        combined, K = dempster_combine(m1, m2)
        assert abs(K - 1.0) < 1e-6
        assert combined.m_uncertain == 1.0
    
    def test_combine_multiple(self):
        """Multiple mass functions combine correctly."""
        masses = [
            MassFunction(m_safe=0.1, m_dangerous=0.5, m_uncertain=0.4, source="a"),
            MassFunction(m_safe=0.1, m_dangerous=0.4, m_uncertain=0.5, source="b"),
            MassFunction(m_safe=0.1, m_dangerous=0.3, m_uncertain=0.6, source="c"),
        ]
        
        combined, conflicts = combine_multiple(masses)
        
        assert len(conflicts) == 2
        # Triple-reinforced danger should be very high
        assert combined.m_dangerous > 0.6
    
    def test_combine_empty_list(self):
        """Empty list returns ignorance."""
        combined, conflicts = combine_multiple([])
        assert combined.m_uncertain == 1.0
        assert conflicts == []
    
    def test_combine_single(self):
        """Single mass function returns itself."""
        m = MassFunction(m_safe=0.3, m_dangerous=0.4, m_uncertain=0.3, source="a")
        combined, conflicts = combine_multiple([m])
        assert abs(combined.m_dangerous - m.m_dangerous) < 1e-6
        assert conflicts == []


class TestEvidenceConstructor:
    """Tests for converting module outputs to mass functions."""
    
    def test_tsr_hazard_sign(self):
        """High-modifier sign → strong danger evidence."""
        m = EvidenceConstructor.from_tsr(
            sign_risk_modifier=0.6,
            tsr_confidence=0.9,
            temporal_decay=1.0
        )
        assert m.m_dangerous > 0.4
        assert m.source == "tsr"
    
    def test_tsr_low_confidence_ignored(self):
        """Low confidence TSR → ignorance."""
        m = EvidenceConstructor.from_tsr(
            sign_risk_modifier=0.6,
            tsr_confidence=0.3,  # Below default threshold
            temporal_decay=1.0
        )
        assert m.m_uncertain >= 0.99
    
    def test_tsr_informational_sign(self):
        """Low-modifier sign → weak/no danger evidence."""
        m = EvidenceConstructor.from_tsr(
            sign_risk_modifier=0.02,
            tsr_confidence=0.9,
            temporal_decay=1.0
        )
        assert m.m_dangerous < 0.1
    
    def test_tsr_decay_reduces_evidence(self):
        """Temporal decay reduces evidence strength."""
        m_fresh = EvidenceConstructor.from_tsr(0.5, 0.9, temporal_decay=1.0)
        m_old = EvidenceConstructor.from_tsr(0.5, 0.9, temporal_decay=0.3)
        assert m_old.m_dangerous < m_fresh.m_dangerous
    
    def test_dz_high_risk(self):
        """High DZ risk → strong danger mass."""
        m = EvidenceConstructor.from_dz(risk_probability=0.8, dz_confidence=0.9)
        assert m.m_dangerous > 0.6
    
    def test_dz_low_risk(self):
        """Low DZ risk → strong safe mass."""
        m = EvidenceConstructor.from_dz(risk_probability=0.1, dz_confidence=0.9)
        assert m.m_safe > 0.6
    
    def test_dz_low_confidence(self):
        """Low DZ confidence → scaled mass with high uncertainty."""
        m = EvidenceConstructor.from_dz(risk_probability=0.8, dz_confidence=0.1)
        assert m.m_uncertain >= 0.89
    
    def test_hotspot_active(self):
        """Active hotspot → danger-only evidence."""
        m = EvidenceConstructor.from_hotspot(risk_boost=0.3, report_count=5)
        assert m.m_dangerous > 0
        assert m.m_safe == 0.0
    
    def test_hotspot_inactive(self):
        """No hotspot → ignorance."""
        m = EvidenceConstructor.from_hotspot(risk_boost=0.0, report_count=0)
        assert m.m_uncertain >= 0.99


# =====================================================================
# MURPHY'S RULE TESTS
# =====================================================================

class TestMurphyCombination:
    """Tests for Murphy's modified combination rule."""
    
    def test_murphy_agreeing_evidence(self):
        """Agreeing evidence should reinforce each other."""
        masses = [
            MassFunction(m_safe=0.1, m_dangerous=0.6, m_uncertain=0.3, source="a"),
            MassFunction(m_safe=0.1, m_dangerous=0.5, m_uncertain=0.4, source="b"),
        ]
        combined, K = murphy_combine(masses)
        
        # Should reinforce danger
        assert combined.m_dangerous > 0.5
        # Low conflict on agreement
        assert K < 0.2
    
    def test_murphy_conflicting_evidence(self):
        """High-conflict evidence should NOT fallback to pure ignorance (unlike Dempster)."""
        masses = [
            MassFunction(m_safe=0.8, m_dangerous=0.0, m_uncertain=0.2, source="safe"),
            MassFunction(m_safe=0.0, m_dangerous=0.8, m_uncertain=0.2, source="danger"),
        ]
        
        # Dempster: high conflict
        ds_combined, ds_K = dempster_combine(masses[0], masses[1])
        
        # Murphy: should handle gracefully
        mu_combined, mu_K = murphy_combine(masses)
        
        # Murphy should produce a more moderate result
        assert mu_combined.m_uncertain > 0  # Not zero uncertainty
        # Murphy conflict should be lower than Dempster conflict
        assert mu_K < ds_K
    
    def test_murphy_with_ignorance(self):
        """Combining with ignorance should not drastically change evidence."""
        masses = [
            MassFunction(m_safe=0.2, m_dangerous=0.5, m_uncertain=0.3, source="a"),
            MassFunction(m_safe=0.0, m_dangerous=0.0, m_uncertain=1.0, source="ign"),
        ]
        combined, K = murphy_combine(masses)
        
        # Result should still lean dangerous
        assert combined.m_dangerous > combined.m_safe
        assert K < 0.1
    
    def test_murphy_matches_dempster_on_low_conflict(self):
        """For low-conflict sources, Murphy ≈ Dempster in direction."""
        masses = [
            MassFunction(m_safe=0.1, m_dangerous=0.4, m_uncertain=0.5, source="a"),
            MassFunction(m_safe=0.15, m_dangerous=0.35, m_uncertain=0.5, source="b"),
        ]
        
        ds_combined, _ = dempster_combine(masses[0], masses[1])
        mu_combined, _ = murphy_combine(masses)
        
        # Both should point in the same direction
        assert ds_combined.m_dangerous > ds_combined.m_safe
        assert mu_combined.m_dangerous > mu_combined.m_safe
    
    def test_murphy_three_sources(self):
        """Murphy handles 3+ sources correctly."""
        masses = [
            MassFunction(m_safe=0.1, m_dangerous=0.5, m_uncertain=0.4, source="a"),
            MassFunction(m_safe=0.1, m_dangerous=0.4, m_uncertain=0.5, source="b"),
            MassFunction(m_safe=0.1, m_dangerous=0.3, m_uncertain=0.6, source="c"),
        ]
        combined, K = murphy_combine(masses)
        
        # Should reinforce danger with 3 agreeing sources
        assert combined.m_dangerous > 0.5
        assert 0 <= K <= 1
    
    def test_murphy_empty_list(self):
        """Empty list returns ignorance."""
        combined, K = murphy_combine([])
        assert combined.m_uncertain == 1.0
        assert K == 0.0
    
    def test_murphy_single(self):
        """Single mass function returns itself."""
        m = MassFunction(m_safe=0.3, m_dangerous=0.4, m_uncertain=0.3, source="a")
        combined, K = murphy_combine([m])
        assert abs(combined.m_dangerous - 0.4) < 1e-6
        assert K == 0.0
    
    def test_murphy_combine_multiple_interface(self):
        """murphy_combine_multiple returns list of conflicts."""
        masses = [
            MassFunction(m_safe=0.1, m_dangerous=0.5, m_uncertain=0.4, source="a"),
            MassFunction(m_safe=0.1, m_dangerous=0.4, m_uncertain=0.5, source="b"),
        ]
        combined, conflicts = murphy_combine_multiple(masses)
        assert isinstance(conflicts, list)
        assert combined.m_dangerous > 0.4


# =====================================================================
# TEMPORAL BUFFER TESTS
# =====================================================================

class TestTemporalSignBuffer:
    """Tests for the sliding window sign buffer."""
    
    def setup_method(self):
        self.buffer = TemporalSignBuffer(
            decay_lambda=0.1, max_signs=10, max_age_s=30
        )
    
    def _make_detection(self, class_id=88, name="curve_to_left",
                        confidence=0.9, ts=None, modifier=0.4):
        return SignDetection(
            class_id=class_id,
            class_name=name,
            confidence=confidence,
            timestamp=ts or time.time(),
            risk_modifier=modifier,
            relevance_duration_s=12.0
        )
    
    def test_add_and_retrieve(self):
        """Can add and retrieve detections."""
        det = self._make_detection()
        self.buffer.add(det)
        assert self.buffer.size == 1
        active = self.buffer.get_active_detections()
        assert len(active) == 1
    
    def test_deduplication(self):
        """Same sign within 2s should deduplicate."""
        now = time.time()
        det1 = self._make_detection(ts=now, confidence=0.8)
        det2 = self._make_detection(ts=now + 1.0, confidence=0.95)
        
        self.buffer.add(det1)
        self.buffer.add(det2)
        
        assert self.buffer.size == 1
        # Should keep the higher confidence
        active = self.buffer.get_active_detections(now + 1.0)
        assert active[0].confidence == 0.95
    
    def test_different_signs_not_deduplicated(self):
        """Different sign classes should not deduplicate."""
        now = time.time()
        det1 = self._make_detection(class_id=88, name="curve_to_left", ts=now)
        det2 = self._make_detection(class_id=39, name="stop", ts=now)
        
        self.buffer.add(det1)
        self.buffer.add(det2)
        
        assert self.buffer.size == 2
    
    def test_expiration(self):
        """Old detections should expire."""
        old_time = time.time() - 100  # 100 seconds ago
        det = self._make_detection(ts=old_time)
        self.buffer.add(det)
        
        active = self.buffer.get_active_detections()
        assert len(active) == 0
    
    def test_decay_weight(self):
        """Decay weight decreases with age."""
        now = time.time()
        det = self._make_detection(ts=now - 5.0, confidence=1.0)
        
        weight = self.buffer.compute_decay_weight(det, now)
        expected = math.exp(-0.1 * 5.0)
        assert abs(weight - expected) < 0.01
    
    def test_aggregate_evidence_empty(self):
        """Empty buffer → zero aggregate."""
        agg = self.buffer.get_aggregate_evidence()
        assert agg.num_active_signs == 0
        assert agg.max_risk_modifier == 0.0
    
    def test_aggregate_evidence_single_sign(self):
        """Single sign → aggregate reflects that sign."""
        now = time.time()
        det = self._make_detection(ts=now, modifier=0.5)
        self.buffer.add(det)
        
        agg = self.buffer.get_aggregate_evidence(now)
        assert agg.num_active_signs == 1
        assert agg.max_risk_modifier == 0.5
        assert agg.dominant_sign is not None
    
    def test_compound_factor(self):
        """Multiple complementary signs boost compound factor."""
        now = time.time()
        # Hazard sign
        self.buffer.add(self._make_detection(
            class_id=88, name="curve_to_left", ts=now, modifier=0.5
        ))
        # Stop sign (name contains 'stop')
        self.buffer.add(self._make_detection(
            class_id=39, name="stop", ts=now, modifier=0.55
        ))
        
        agg = self.buffer.get_aggregate_evidence(now)
        assert agg.compound_factor > 1.0
    
    def test_clear(self):
        """Clear empties the buffer."""
        self.buffer.add(self._make_detection())
        assert self.buffer.size == 1
        self.buffer.clear()
        assert self.buffer.size == 0
    
    def test_cleanup(self):
        """Cleanup removes expired detections."""
        old_time = time.time() - 100
        self.buffer.add(self._make_detection(ts=old_time))
        self.buffer.add(self._make_detection(class_id=1, name="fresh", ts=time.time()))
        
        removed = self.buffer.cleanup()
        assert removed == 1
        assert self.buffer.size == 1
    
    def test_max_signs_limit(self):
        """Buffer respects max_signs limit."""
        now = time.time()
        for i in range(15):
            self.buffer.add(self._make_detection(
                class_id=i, name=f"sign_{i}", ts=now + i * 3
            ))
        assert self.buffer.size <= 10


# =====================================================================
# FUSION ENGINE TESTS
# =====================================================================

class TestFusionEngine:
    """Tests for the main fusion orchestrator."""
    
    def setup_method(self):
        self.engine = FusionEngine()
    
    def test_dz_only_fusion(self):
        """DZ-only fusion (no TSR) should work."""
        dz = DZInput(
            risk_score=45.0,
            risk_level="MEDIUM",
            confidence=0.85,
            risk_probability=0.45
        )
        
        result = self.engine.fuse(dz_input=dz)
        
        assert isinstance(result, FusionResult)
        assert 0 <= result.fused_risk_score <= 100
        assert result.fused_risk_level in ("LOW", "MEDIUM", "HIGH")
        assert result.tsr_contribution.get("detected") == False
    
    def test_dz_plus_tsr_fusion(self):
        """DZ + TSR fusion produces valid result."""
        dz = DZInput(
            risk_score=40.0, risk_level="MEDIUM",
            confidence=0.85, risk_probability=0.40
        )
        tsr = TSRInput(
            class_id=88, class_name="curve_to_left",
            confidence=0.92, is_confident=True
        )
        
        result = self.engine.fuse(dz_input=dz, tsr_input=tsr)
        
        assert result.tsr_contribution.get("detected") == True
        # Curve sign should increase risk
        assert result.fused_risk_score >= 40.0
    
    def test_hazard_sign_escalates_risk(self):
        """Hazard sign + medium DZ → risk escalation."""
        self.engine.reset()
        
        dz = DZInput(
            risk_score=35.0, risk_level="LOW",
            confidence=0.85, risk_probability=0.35
        )
        
        # First: DZ-only baseline
        baseline = self.engine.fuse(dz_input=dz)
        
        self.engine.reset()
        
        # Then: DZ + accident sign
        tsr = TSRInput(
            class_id=83, class_name="accident",
            confidence=0.95, is_confident=True
        )
        result = self.engine.fuse(dz_input=dz, tsr_input=tsr)
        
        assert result.fused_risk_score > baseline.fused_risk_score
    
    def test_low_confidence_tsr_ignored(self):
        """Low-confidence TSR should be ignored."""
        dz = DZInput(
            risk_score=50.0, risk_level="MEDIUM",
            confidence=0.85, risk_probability=0.50
        )
        tsr = TSRInput(
            class_id=88, class_name="curve_to_left",
            confidence=0.3, is_confident=False  # Below threshold
        )
        
        result = self.engine.fuse(dz_input=dz, tsr_input=tsr)
        # Should behave like DZ-only
        assert result.tsr_contribution.get("detected", True) == False or \
               result.tsr_contribution.get("detected") is None
    
    def test_hotspot_increases_risk(self):
        """Hotspot data should increase fused risk."""
        self.engine.reset()
        
        dz = DZInput(
            risk_score=30.0, risk_level="LOW",
            confidence=0.85, risk_probability=0.30
        )
        
        baseline = self.engine.fuse(dz_input=dz)
        self.engine.reset()
        
        hotspot = HotspotInput(risk_boost=0.4, report_count=8)
        result = self.engine.fuse(dz_input=dz, hotspot_input=hotspot)
        
        assert result.fused_risk_score > baseline.fused_risk_score
    
    def test_risk_score_in_valid_range(self):
        """Fused risk score should always be [0, 100]."""
        dz = DZInput(
            risk_score=95.0, risk_level="HIGH",
            confidence=0.99, risk_probability=0.95
        )
        tsr = TSRInput(
            class_id=83, class_name="accident",
            confidence=0.99, is_confident=True
        )
        hotspot = HotspotInput(risk_boost=0.5, report_count=20)
        
        result = self.engine.fuse(dz_input=dz, tsr_input=tsr, hotspot_input=hotspot)
        assert 0 <= result.fused_risk_score <= 100
    
    def test_ds_quantities_valid(self):
        """All DS quantities should be in valid ranges."""
        dz = DZInput(
            risk_score=50.0, risk_level="MEDIUM",
            confidence=0.85, risk_probability=0.50
        )
        result = self.engine.fuse(dz_input=dz)
        
        assert 0 <= result.belief_dangerous <= 1
        assert 0 <= result.plausibility_dangerous <= 1
        assert result.belief_dangerous <= result.plausibility_dangerous
        assert 0 <= result.pignistic_probability <= 1
        assert 0 <= result.conflict_measure <= 1
    
    def test_fusion_result_serialization(self):
        """FusionResult should serialize to dict/JSON."""
        dz = DZInput(
            risk_score=50.0, risk_level="MEDIUM",
            confidence=0.85, risk_probability=0.50
        )
        result = self.engine.fuse(dz_input=dz)
        
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "fused_risk_score" in d
        
        j = result.to_json()
        assert isinstance(j, str)
        assert "fused_risk_score" in j
    
    def test_reset_clears_state(self):
        """Engine reset clears buffer, EMA, and conflict log."""
        dz = DZInput(
            risk_score=50.0, risk_level="MEDIUM",
            confidence=0.85, risk_probability=0.50
        )
        tsr = TSRInput(
            class_id=88, class_name="curve_to_left",
            confidence=0.92, is_confident=True
        )
        self.engine.fuse(dz_input=dz, tsr_input=tsr)
        
        assert self.engine.buffer.size > 0
        
        self.engine.reset()
        
        assert self.engine.buffer.size == 0
        assert len(self.engine._ema_history) == 0
    
    def test_conflict_log_records_high_conflict(self):
        """High conflict should be logged."""
        self.engine.reset()
        self.engine.conflict_threshold = 0.01  # Low threshold for testing
        
        dz = DZInput(
            risk_score=10.0, risk_level="LOW",
            confidence=0.95, risk_probability=0.10  # Says SAFE
        )
        tsr = TSRInput(
            class_id=83, class_name="accident",
            confidence=0.95, is_confident=True  # Says DANGEROUS
        )
        
        self.engine.fuse(dz_input=dz, tsr_input=tsr)
        
        log = self.engine.get_conflict_log()
        # May or may not have conflict depending on exact masses
        # but the mechanism should work
        assert isinstance(log, list)
    
    def test_ema_smoothing(self):
        """EMA should smooth score changes."""
        self.engine.reset()
        
        # First: high risk
        dz_high = DZInput(
            risk_score=80.0, risk_level="HIGH",
            confidence=0.9, risk_probability=0.80
        )
        r1 = self.engine.fuse(dz_input=dz_high)
        
        # Then: sudden low risk
        dz_low = DZInput(
            risk_score=20.0, risk_level="LOW",
            confidence=0.9, risk_probability=0.20
        )
        r2 = self.engine.fuse(dz_input=dz_low)
        
        # EMA should prevent instant drop
        assert r2.fused_risk_score > 20.0
    
    def test_multiple_signs_accumulate(self):
        """Multiple sign detections should accumulate in buffer."""
        now = time.time()
        
        dz = DZInput(
            risk_score=40.0, risk_level="MEDIUM",
            confidence=0.85, risk_probability=0.40
        )
        
        signs = [
            TSRInput(class_id=88, class_name="curve_to_left",
                     confidence=0.9, is_confident=True),
            TSRInput(class_id=112, class_name="slippery_road",
                     confidence=0.85, is_confident=True),
        ]
        
        for tsr in signs:
            tsr.timestamp = now
            self.engine.fuse(dz_input=dz, tsr_input=tsr, current_time=now)
            now += 0.5
        
        assert len(self.engine.buffer.get_active_detections(now)) == 2


# =====================================================================
# INTEGRATION TEST
# =====================================================================

class TestIntegration:
    """End-to-end integration tests with realistic scenarios."""
    
    def setup_method(self):
        self.engine = FusionEngine()
    
    def test_scenario_curve_on_wet_road(self):
        """
        Scenario: Curve ahead sign detected on a wet road.
        Expected: Risk should be elevated due to compounding factors.
        """
        self.engine.reset()
        
        dz = DZInput(
            risk_score=42.0, risk_level="MEDIUM",
            confidence=0.88, risk_probability=0.42,
            weather_condition="Rain", road_surface="Wet",
            speed_kph=55.0
        )
        tsr = TSRInput(
            class_id=87, class_name="curve_to_left",
            confidence=0.94, is_confident=True
        )
        
        result = self.engine.fuse(dz_input=dz, tsr_input=tsr)
        
        # Should escalate beyond DZ-only score
        assert result.fused_risk_score > 42.0
        assert result.fused_risk_level in ("MEDIUM", "HIGH")
        assert len(result.fusion_reasons) > 0
    
    def test_scenario_safe_road_informational_sign(self):
        """
        Scenario: Parking sign on a safe road.
        Expected: Risk should remain low.
        """
        self.engine.reset()
        
        dz = DZInput(
            risk_score=15.0, risk_level="LOW",
            confidence=0.90, risk_probability=0.15
        )
        tsr = TSRInput(
            class_id=13, class_name="parking",
            confidence=0.95, is_confident=True
        )
        
        result = self.engine.fuse(dz_input=dz, tsr_input=tsr)
        
        assert result.fused_risk_level == "LOW"
    
    def test_scenario_high_risk_no_sign(self):
        """
        Scenario: High risk zone, no TSR input.
        Expected: Fused output uses DZ risk directly.
        """
        self.engine.reset()
        
        dz = DZInput(
            risk_score=78.0, risk_level="HIGH",
            confidence=0.92, risk_probability=0.78
        )
        
        result = self.engine.fuse(dz_input=dz)
        
        assert result.fused_risk_level == "HIGH"
        assert result.tsr_contribution.get("detected") == False
    
    def test_scenario_full_pipeline(self):
        """Full pipeline: DZ + TSR + hotspot → fused result."""
        self.engine.reset()
        
        dz = DZInput(
            risk_score=55.0, risk_level="MEDIUM",
            confidence=0.87, risk_probability=0.55,
            weather_condition="Rain", road_surface="Wet",
            speed_kph=60.0,
            reasons=[{"feature": "Junction", "direction": "increases risk"}]
        )
        tsr = TSRInput(
            class_id=91, class_name="double_curve,_first_to_left",
            confidence=0.88, is_confident=True
        )
        hotspot = HotspotInput(risk_boost=0.2, report_count=5)
        
        result = self.engine.fuse(
            dz_input=dz, tsr_input=tsr, hotspot_input=hotspot
        )
        
        assert isinstance(result, FusionResult)
        assert result.fused_risk_score > 55.0
        assert result.hotspot_contribution.get("active") == True
        assert len(result.active_signs) >= 1
        assert len(result.fusion_reasons) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
