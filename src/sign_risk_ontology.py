"""
Sign-Risk Ontology Module
Maps 122 Sri Lankan traffic sign classes to risk-relevant categories
with quantified impact weights and contextual modifiers.

This ontology is the knowledge bridge between the Traffic Sign Recognition (TSR)
module's visual perception output and the Dangerous Zone (DZ) module's structured
risk prediction. Each sign class is annotated with:
  - risk_category: Semantic grouping (hazard, regulatory, informational, etc.)
  - base_risk_modifier: Quantified impact on zone risk score [0.0, 1.0]
  - relevance_duration_s: Temporal window of influence after detection
  - contextual_rules: Conditional modifiers based on environmental state

References:
  - Vienna Convention on Road Signs and Signals (1968)
  - Sri Lanka Department of Motor Traffic signage standards
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable


class SignRiskCategory(Enum):
    """Semantic categories for traffic sign risk classification."""
    HAZARD_WARNING     = "hazard_warning"       # Curve, slippery, falling rocks, etc.
    SPEED_REGULATORY   = "speed_regulatory"     # Speed limit signs
    PROHIBITION        = "prohibition"          # No entry, no overtaking, etc.
    MANDATORY          = "mandatory"            # Keep left, roundabout, proceed straight
    PRIORITY           = "priority"             # Stop, give way, priority road
    TRAFFIC_SIGNAL     = "traffic_signal"       # Red/yellow/green lights
    INFORMATIONAL      = "informational"        # Direction, distance, parking, facilities
    ROAD_MARKING       = "road_marking"         # Overtaking line, warning line


class ContextCondition(Enum):
    """Environmental conditions that modify sign risk impact."""
    RAIN          = "rain"
    NIGHT         = "night"
    FOG           = "fog"
    WET_SURFACE   = "wet_surface"
    PEAK_HOUR     = "peak_hour"
    HIGH_SPEED    = "high_speed"       # Vehicle speed > 60 kph
    OVERSPEEDING  = "overspeeding"     # Vehicle speed > road limit


@dataclass
class ContextualRule:
    """
    A conditional modifier that adjusts risk impact based on environmental state.
    
    When the condition is met, the base_risk_modifier is multiplied by `multiplier`.
    Example: 'slippery_road' sign has 2.0x impact when it's raining.
    """
    condition: ContextCondition
    multiplier: float
    description: str


@dataclass
class SignRiskProfile:
    """
    Complete risk profile for a single traffic sign class.
    
    Attributes:
        class_id: Integer class index from TSR model (0-121)
        class_name: Human-readable sign name
        risk_category: Semantic category
        base_risk_modifier: Base impact on danger zone risk [0.0, 1.0]
            0.0 = no impact (pure informational)
            0.1-0.2 = mild (general awareness signs)
            0.2-0.4 = moderate (regulatory/mandatory)
            0.4-0.6 = significant (hazard warnings)
            0.6-0.8 = high (immediate danger warnings)
            0.8-1.0 = critical (stop, accident ahead)
        relevance_duration_s: How long the sign influences risk after detection
        contextual_rules: Conditional modifiers
        sign_speed_kph: For speed limit signs, the indicated speed
        is_speed_sign: Whether this sign indicates a speed limit
    """
    class_id: int
    class_name: str
    risk_category: SignRiskCategory
    base_risk_modifier: float
    relevance_duration_s: float = 15.0
    contextual_rules: List[ContextualRule] = field(default_factory=list)
    sign_speed_kph: Optional[float] = None
    is_speed_sign: bool = False


class SignRiskOntology:
    """
    Knowledge base mapping all 122 Sri Lankan traffic sign classes
    to their risk-relevant metadata.
    
    Usage:
        ontology = SignRiskOntology()
        profile = ontology.get_profile(class_id=88)  # "curve_to_left"
        modifier = ontology.compute_effective_modifier(
            profile, weather_code=2, is_night=False, speed_kph=50
        )
    """
    
    def __init__(self):
        self._profiles: Dict[int, SignRiskProfile] = {}
        self._name_to_id: Dict[str, int] = {}
        self._build_ontology()
    
    def _build_ontology(self):
        """Construct the complete sign-risk knowledge base."""
        
        # =====================================================================
        # INFORMATIONAL SIGNS (class_ids 0-20) -- Low risk impact
        # These provide information but don't indicate immediate danger
        # =====================================================================
        informational_signs = {
            0:  ("end_of_motorway", 0.05, 10.0),
            1:  ("expressway", 0.02, 20.0),
            2:  ("motorway", 0.02, 20.0),
            3:  ("exit_ramp", 0.10, 8.0),     # Slight risk during lane change
            4:  ("caravan_site", 0.0, 5.0),
            5:  ("cul_de_sac", 0.02, 10.0),
            6:  ("emergency_telephone", 0.0, 5.0),
            7:  ("end_of_living_street", 0.03, 8.0),
            8:  ("first_aid", 0.0, 5.0),
            9:  ("hospital", 0.05, 15.0),     # Expect pedestrians
            10: ("light_refreshment", 0.0, 5.0),
            11: ("living_street", 0.10, 15.0),  # Low speed zone, pedestrians
            12: ("one_way_street", 0.05, 15.0),
            13: ("parking", 0.03, 8.0),
            14: ("pedestrian_crossing", 0.25, 10.0),  # Significant - pedestrian risk
            15: ("petrol_station", 0.02, 5.0),
            16: ("restaurant", 0.0, 5.0),
            17: ("swimming_pool", 0.0, 5.0),
            18: ("telephone", 0.0, 5.0),
            19: ("youth_hostel", 0.0, 5.0),
            20: ("beginning_of_an_administrative_area", 0.02, 10.0),
            21: ("confirming_distances", 0.0, 5.0),
            22: ("direction_sign", 0.02, 5.0),
            23: ("light_signals_for_pedestrians", 0.15, 10.0),
        }
        
        for cid, (name, modifier, duration) in informational_signs.items():
            rules = []
            # Pedestrian-related informational signs are more dangerous at night
            if name in ("pedestrian_crossing", "hospital", "living_street",
                        "light_signals_for_pedestrians"):
                rules.append(ContextualRule(
                    ContextCondition.NIGHT, 1.5,
                    "Pedestrian areas are higher risk at night"
                ))
                rules.append(ContextualRule(
                    ContextCondition.RAIN, 1.3,
                    "Reduced visibility near pedestrian zones in rain"
                ))
            
            self._register(SignRiskProfile(
                class_id=cid,
                class_name=name,
                risk_category=SignRiskCategory.INFORMATIONAL,
                base_risk_modifier=modifier,
                relevance_duration_s=duration,
                contextual_rules=rules
            ))
        
        # =====================================================================
        # SUPPLEMENTARY SIGNS (class_ids 24-25) -- Context-specific
        # =====================================================================
        self._register(SignRiskProfile(
            class_id=24,
            class_name="5.00_am___9.00_pm_(supplementing_a_regulatory_sign)",
            risk_category=SignRiskCategory.INFORMATIONAL,
            base_risk_modifier=0.05,
            relevance_duration_s=10.0
        ))
        self._register(SignRiskProfile(
            class_id=25,
            class_name="school_(supplementing_a_regulatory_sign)",
            risk_category=SignRiskCategory.HAZARD_WARNING,
            base_risk_modifier=0.35,
            relevance_duration_s=20.0,
            contextual_rules=[
                ContextualRule(ContextCondition.PEAK_HOUR, 1.8,
                               "School zone during peak hours = high pedestrian activity"),
                ContextualRule(ContextCondition.RAIN, 1.3,
                               "Children may run across roads in rain")
            ]
        ))
        
        # =====================================================================
        # MANDATORY SIGNS (class_ids 26-33) -- Moderate risk
        # These dictate required driver actions
        # =====================================================================
        mandatory_signs = {
            26: ("pass_onto_left", 0.15, 10.0),
            27: ("pass_onto_right", 0.15, 10.0),
            28: ("proceed_straight", 0.10, 10.0),
            29: ("roundabout", 0.25, 15.0),   # Complex traffic interaction
            30: ("turn_left_ahead", 0.15, 10.0),
            31: ("turn_left", 0.15, 10.0),
            32: ("turn_right_ahead", 0.15, 10.0),
            33: ("turn_right", 0.15, 10.0),
        }
        
        for cid, (name, modifier, duration) in mandatory_signs.items():
            rules = [
                ContextualRule(ContextCondition.HIGH_SPEED, 1.4,
                               "Mandatory maneuver at high speed increases risk"),
                ContextualRule(ContextCondition.WET_SURFACE, 1.3,
                               "Turning/maneuvering on wet surface")
            ]
            if name == "roundabout":
                rules.append(ContextualRule(
                    ContextCondition.PEAK_HOUR, 1.5,
                    "Roundabouts are congested during peak hours"
                ))
            
            self._register(SignRiskProfile(
                class_id=cid,
                class_name=name,
                risk_category=SignRiskCategory.MANDATORY,
                base_risk_modifier=modifier,
                relevance_duration_s=duration,
                contextual_rules=rules
            ))
        
        # =====================================================================
        # PRIORITY SIGNS (class_ids 34-39) -- High risk
        # These indicate right-of-way situations requiring careful attention
        # =====================================================================
        priority_signs = {
            34: ("end_of_priority_road", 0.20, 12.0),
            35: ("give_way_to_oncoming_traffic", 0.40, 12.0),
            36: ("give_way", 0.45, 12.0),
            37: ("priority_over_oncoming_traffic", 0.10, 12.0),
            38: ("priority_road", 0.05, 15.0),
            39: ("stop", 0.55, 15.0),
        }
        
        for cid, (name, modifier, duration) in priority_signs.items():
            rules = [
                ContextualRule(ContextCondition.NIGHT, 1.4,
                               "Priority/junction decisions harder at night"),
                ContextualRule(ContextCondition.RAIN, 1.3,
                               "Stopping distance increases in rain"),
                ContextualRule(ContextCondition.OVERSPEEDING, 1.6,
                               "Cannot stop in time if overspeeding at priority sign")
            ]
            self._register(SignRiskProfile(
                class_id=cid,
                class_name=name,
                risk_category=SignRiskCategory.PRIORITY,
                base_risk_modifier=modifier,
                relevance_duration_s=duration,
                contextual_rules=rules
            ))
        
        # =====================================================================
        # PROHIBITION SIGNS (class_ids 40-65) -- Moderate-High risk
        # These prohibit certain actions; violation implies danger
        # =====================================================================
        prohibition_signs = {
            40: ("all_vehicles_prohibited", 0.35, 15.0),
            41: ("maximum_length", 0.10, 10.0),
            42: ("minimum_safe_distance", 0.20, 12.0),
            43: ("no_animal_drawn_vehicles", 0.05, 10.0),
            44: ("no_bicycles", 0.05, 10.0),
            45: ("no_entry", 0.50, 15.0),        # High risk - wrong way
            46: ("no_handcarts", 0.05, 10.0),
            47: ("no_horns", 0.05, 12.0),         # Usually near hospitals/schools
            48: ("no_left_turn", 0.20, 10.0),
            49: ("no_mopeds", 0.05, 10.0),
            50: ("no_motor_vehicles,_except_motorcycles", 0.10, 10.0),
            51: ("no_motor_vehicles", 0.15, 10.0),
            52: ("no_motorcycles", 0.05, 10.0),
            53: ("no_overtaking_by_trucks", 0.20, 15.0),
            54: ("no_overtaking", 0.30, 15.0),   # Usually on dangerous stretches
            55: ("no_parking_and_standing", 0.05, 8.0),
            56: ("no_parking_on_even_numbered_days", 0.03, 8.0),
            57: ("no_parking_on_odd_numbered_days", 0.03, 8.0),
            58: ("no_parking", 0.03, 8.0),
            59: ("no_pedestrians", 0.05, 10.0),
            60: ("no_right_turn", 0.20, 10.0),
            61: ("no_tractors", 0.05, 10.0),
            62: ("no_trailers_2", 0.05, 10.0),
            63: ("no_trailers", 0.05, 10.0),
            64: ("no_trucks", 0.10, 10.0),
            65: ("no_u_turn", 0.25, 10.0),
        }
        
        for cid, (name, modifier, duration) in prohibition_signs.items():
            rules = []
            # No overtaking signs indicate dangerous road geometry
            if "overtaking" in name:
                rules.extend([
                    ContextualRule(ContextCondition.HIGH_SPEED, 1.5,
                                   "Dangerous overtaking at high speed"),
                    ContextualRule(ContextCondition.WET_SURFACE, 1.4,
                                   "Overtaking prohibition on wet roads")
                ])
            # No entry is always critical
            if name == "no_entry":
                rules.append(ContextualRule(
                    ContextCondition.NIGHT, 1.6,
                    "Wrong-way entry risk increases at night"
                ))
            
            self._register(SignRiskProfile(
                class_id=cid,
                class_name=name,
                risk_category=SignRiskCategory.PROHIBITION,
                base_risk_modifier=modifier,
                relevance_duration_s=duration,
                contextual_rules=rules
            ))
        
        # =====================================================================
        # SPEED REGULATORY SIGNS (class_ids 66-75) -- Moderate risk
        # Speed limits and vehicle dimension restrictions
        # =====================================================================
        self._register(SignRiskProfile(
            class_id=66,
            class_name="height_limit",
            risk_category=SignRiskCategory.SPEED_REGULATORY,
            base_risk_modifier=0.15,
            relevance_duration_s=10.0
        ))
        
        # Speed limit signs — the speed value affects risk scoring differently
        speed_signs = {
            67: ("maximum_speed_limit_(3_wheelers_and_land_vehicles_in_built_up_and_non_built_up_areas)", 40.0),
            68: ("maximum_speed_limit_(all_vehicles_within_school_areas_and_hospitals)", 20.0),
            69: ("maximum_speed_limit_(heavy_vehicles_in_non_built_up_areas)", 50.0),
            70: ("maximum_speed_limit_(light_vehicles_outside_built_up_areas)", 70.0),
            71: ("maximum_speed_limit_(vehicles_within_built_up_areas_except_for_3_wheelers_and_land_vehicles)", 50.0),
            72: ("maximum_speed_limit_ends", None),
        }
        
        for cid, (name, speed) in speed_signs.items():
            # Lower speed limits indicate more dangerous areas
            if speed is not None:
                if speed <= 20:
                    modifier = 0.30    # School/hospital zone
                elif speed <= 40:
                    modifier = 0.20    # Built-up area
                elif speed <= 50:
                    modifier = 0.15    # Standard urban
                else:
                    modifier = 0.10    # Rural/highway
            else:
                modifier = 0.05  # End of speed limit
            
            rules = [
                ContextualRule(ContextCondition.OVERSPEEDING, 1.8,
                               "Exceeding posted speed limit is very dangerous")
            ]
            if speed is not None and speed <= 30:
                rules.append(ContextualRule(
                    ContextCondition.PEAK_HOUR, 1.5,
                    "School/hospital zones during peak hours"
                ))
            
            self._register(SignRiskProfile(
                class_id=cid,
                class_name=name,
                risk_category=SignRiskCategory.SPEED_REGULATORY,
                base_risk_modifier=modifier,
                relevance_duration_s=20.0,
                contextual_rules=rules,
                sign_speed_kph=speed,
                is_speed_sign=True
            ))
        
        # Weight and width limits
        for cid, name in [(73, "weight_limit_on_one_axle"), (74, "weight_limit"), (75, "width_limit")]:
            self._register(SignRiskProfile(
                class_id=cid,
                class_name=name,
                risk_category=SignRiskCategory.SPEED_REGULATORY,
                base_risk_modifier=0.10,
                relevance_duration_s=10.0
            ))
        
        # =====================================================================
        # ROAD MARKING SIGNS (class_ids 76-78) -- Low-Moderate risk
        # =====================================================================
        road_markings = {
            76: ("cycle_crossing", 0.20, 10.0),
            77: ("overtaking_line", 0.05, 15.0),
            78: ("warning_line", 0.15, 15.0),
        }
        
        for cid, (name, modifier, duration) in road_markings.items():
            rules = []
            if name == "cycle_crossing":
                rules.append(ContextualRule(
                    ContextCondition.NIGHT, 1.5,
                    "Cyclists less visible at night"
                ))
            self._register(SignRiskProfile(
                class_id=cid,
                class_name=name,
                risk_category=SignRiskCategory.ROAD_MARKING,
                base_risk_modifier=modifier,
                relevance_duration_s=duration,
                contextual_rules=rules
            ))
        
        # =====================================================================
        # TRAFFIC SIGNAL SIGNS (class_ids 79-82) -- Variable risk
        # =====================================================================
        traffic_signals = {
            79: ("green_traffic_light", 0.05, 8.0),
            80: ("red_&_yellow_traffic_light", 0.35, 10.0),  # Transition phase
            81: ("red_traffic_light", 0.45, 10.0),           # Must stop
            82: ("yellow_traffic_light", 0.30, 8.0),         # Caution phase
        }
        
        for cid, (name, modifier, duration) in traffic_signals.items():
            rules = [
                ContextualRule(ContextCondition.OVERSPEEDING, 1.7,
                               "Cannot stop for traffic light if overspeeding")
            ]
            if "red" in name:
                rules.append(ContextualRule(
                    ContextCondition.HIGH_SPEED, 1.5,
                    "Approaching red light at high speed"
                ))
            self._register(SignRiskProfile(
                class_id=cid,
                class_name=name,
                risk_category=SignRiskCategory.TRAFFIC_SIGNAL,
                base_risk_modifier=modifier,
                relevance_duration_s=duration,
                contextual_rules=rules
            ))
        
        # =====================================================================
        # HAZARD WARNING SIGNS (class_ids 83-121) -- HIGH risk
        # These are the most safety-critical signs
        # =====================================================================
        hazard_signs = {
            83:  ("accident", 0.80, 20.0),           # Accident ahead!
            84:  ("animals", 0.35, 15.0),
            85:  ("bump", 0.30, 10.0),
            86:  ("children", 0.45, 20.0),            # High pedestrian risk
            87:  ("curve_to_left", 0.40, 12.0),
            88:  ("curve_to_right", 0.40, 12.0),
            89:  ("cyclists", 0.30, 12.0),
            90:  ("dip", 0.25, 10.0),
            91:  ("double_curve,_first_to_left", 0.50, 15.0),
            92:  ("double_curve,_first_to_right", 0.50, 15.0),
            93:  ("drawbridge", 0.40, 15.0),
            94:  ("falling_rocks", 0.55, 15.0),
            95:  ("fog", 0.50, 20.0),
            96:  ("give_way_ahead", 0.35, 12.0),
            97:  ("intersection_with_a_secondary_road", 0.25, 12.0),
            98:  ("intersection_with_a_side_road_at_right_angles", 0.30, 12.0),
            99:  ("joining_a_side_road_at_right_angles_to_the_left", 0.25, 12.0),
            100: ("joining_a_side_road_at_right_angles_to_the_right", 0.25, 12.0),
            101: ("level_crossing_with_barriers_ahead", 0.40, 15.0),
            102: ("level_crossing_without_barriers_ahead", 0.55, 15.0),
            103: ("loose_gravel", 0.35, 12.0),
            104: ("multi_track_level_crossing", 0.45, 15.0),
            105: ("other_dangers", 0.40, 15.0),
            106: ("quayside_or_riverbank", 0.45, 15.0),
            107: ("road_narrows_on_left_side", 0.35, 12.0),
            108: ("road_narrows_on_right_side", 0.35, 12.0),
            109: ("road_narrows", 0.35, 12.0),
            110: ("roadworks", 0.45, 20.0),
            111: ("single_track_level_crossing", 0.50, 15.0),
            112: ("slippery_road", 0.50, 15.0),
            113: ("soft_verges", 0.25, 12.0),
            114: ("steep_ascent", 0.30, 15.0),
            115: ("steep_descent", 0.35, 15.0),
            116: ("stop_sign_ahead", 0.45, 12.0),
            117: ("traffic_light", 0.20, 12.0),
            118: ("tunnel", 0.35, 15.0),
            119: ("two_way_traffic", 0.30, 15.0),
            120: ("uneven_road", 0.30, 12.0),
            121: ("wild_animals", 0.40, 15.0),
        }
        
        for cid, (name, modifier, duration) in hazard_signs.items():
            rules = []
            
            # Curve-related signs: much worse on wet roads
            if "curve" in name:
                rules.extend([
                    ContextualRule(ContextCondition.WET_SURFACE, 1.8,
                                   "Curves are very dangerous on wet surfaces"),
                    ContextualRule(ContextCondition.HIGH_SPEED, 1.6,
                                   "Approaching curve at high speed"),
                    ContextualRule(ContextCondition.NIGHT, 1.3,
                                   "Curves harder to judge at night")
                ])
            
            # Slippery road: massively worse in rain
            if name == "slippery_road":
                rules.extend([
                    ContextualRule(ContextCondition.RAIN, 2.0,
                                   "Slippery road warning + active rain = extreme danger"),
                    ContextualRule(ContextCondition.WET_SURFACE, 1.8,
                                   "Already wet surface with slippery road warning"),
                    ContextualRule(ContextCondition.HIGH_SPEED, 1.7,
                                   "High speed on slippery road")
                ])
            
            # Fog warning: worse at night or with actual fog
            if name == "fog":
                rules.extend([
                    ContextualRule(ContextCondition.FOG, 2.0,
                                   "Fog warning confirmed by actual foggy conditions"),
                    ContextualRule(ContextCondition.NIGHT, 1.8,
                                   "Fog at night severely reduces visibility")
                ])
            
            # Pedestrian/cyclist hazards: worse at night and peak hours
            if name in ("children", "cyclists"):
                rules.extend([
                    ContextualRule(ContextCondition.NIGHT, 1.6,
                                   f"{name.capitalize()} less visible at night"),
                    ContextualRule(ContextCondition.PEAK_HOUR, 1.5,
                                   f"More {name} during peak hours"),
                    ContextualRule(ContextCondition.RAIN, 1.3,
                                   f"{name.capitalize()} may behave unpredictably in rain")
                ])
            
            # Level crossings: always critical
            if "level_crossing" in name:
                rules.extend([
                    ContextualRule(ContextCondition.NIGHT, 1.5,
                                   "Level crossings harder to see at night"),
                    ContextualRule(ContextCondition.OVERSPEEDING, 2.0,
                                   "Cannot stop at level crossing if overspeeding")
                ])
            
            # Road geometry hazards: worse in adverse weather
            if name in ("steep_descent", "steep_ascent", "loose_gravel",
                        "bump", "dip", "uneven_road", "soft_verges"):
                rules.extend([
                    ContextualRule(ContextCondition.WET_SURFACE, 1.5,
                                   f"{name.replace('_', ' ').capitalize()} worse on wet surface"),
                    ContextualRule(ContextCondition.HIGH_SPEED, 1.4,
                                   f"Road hazard at high speed")
                ])
            
            # Accident ahead: always max severity
            if name == "accident":
                rules.extend([
                    ContextualRule(ContextCondition.NIGHT, 1.3,
                                   "Accident scene harder to see at night"),
                    ContextualRule(ContextCondition.HIGH_SPEED, 1.5,
                                   "Approaching accident at high speed")
                ])
            
            # Road narrowing: worse with oncoming traffic context
            if "narrows" in name:
                rules.append(ContextualRule(
                    ContextCondition.PEAK_HOUR, 1.4,
                    "Narrow road during peak traffic"
                ))
            
            # Roadworks: extended duration and worse at night
            if name == "roadworks":
                rules.extend([
                    ContextualRule(ContextCondition.NIGHT, 1.5,
                                   "Roadworks less visible at night"),
                    ContextualRule(ContextCondition.HIGH_SPEED, 1.4,
                                   "Approaching roadworks at high speed")
                ])
            
            # Tunnel: always dangerous in combo conditions
            if name == "tunnel":
                rules.extend([
                    ContextualRule(ContextCondition.HIGH_SPEED, 1.4,
                                   "High speed in tunnel reduces reaction time"),
                ])
            
            self._register(SignRiskProfile(
                class_id=cid,
                class_name=name,
                risk_category=SignRiskCategory.HAZARD_WARNING,
                base_risk_modifier=modifier,
                relevance_duration_s=duration,
                contextual_rules=rules
            ))
    
    def _register(self, profile: SignRiskProfile):
        """Register a sign risk profile."""
        self._profiles[profile.class_id] = profile
        self._name_to_id[profile.class_name] = profile.class_id
    
    def get_profile(self, class_id: int) -> Optional[SignRiskProfile]:
        """Get risk profile by class ID."""
        return self._profiles.get(class_id)
    
    def get_profile_by_name(self, class_name: str) -> Optional[SignRiskProfile]:
        """Get risk profile by class name."""
        cid = self._name_to_id.get(class_name)
        if cid is not None:
            return self._profiles.get(cid)
        return None
    
    def compute_effective_modifier(
        self,
        profile: SignRiskProfile,
        weather_code: int = 1,
        is_night: bool = False,
        is_fog: bool = False,
        is_wet: bool = False,
        is_peak_hour: bool = False,
        speed_kph: float = 40.0,
        speed_limit_kph: float = 50.0
    ) -> float:
        """
        Compute context-adjusted risk modifier for a sign.
        
        Applies contextual rules based on current environmental conditions,
        then clamps the result to [0.0, 1.0].
        
        Args:
            profile: The sign's risk profile
            weather_code: DZ weather condition code (1=Fine, 2=Rain, 7=Fog, etc.)
            is_night: Whether it's nighttime
            is_fog: Whether fog is present
            is_wet: Whether road surface is wet
            is_peak_hour: Whether it's peak traffic hour
            speed_kph: Current vehicle speed
            speed_limit_kph: Road speed limit
            
        Returns:
            Effective risk modifier in [0.0, 1.0]
        """
        modifier = profile.base_risk_modifier
        
        # Determine active conditions
        active_conditions = set()
        if weather_code in (2, 5):  # Rain or Rain+Wind
            active_conditions.add(ContextCondition.RAIN)
        if is_night:
            active_conditions.add(ContextCondition.NIGHT)
        if is_fog or weather_code == 7:
            active_conditions.add(ContextCondition.FOG)
        if is_wet:
            active_conditions.add(ContextCondition.WET_SURFACE)
        if is_peak_hour:
            active_conditions.add(ContextCondition.PEAK_HOUR)
        if speed_kph > 60:
            active_conditions.add(ContextCondition.HIGH_SPEED)
        if speed_kph > speed_limit_kph * 1.1:
            active_conditions.add(ContextCondition.OVERSPEEDING)
        
        # Apply all matching contextual rules
        max_multiplier = 1.0
        for rule in profile.contextual_rules:
            if rule.condition in active_conditions:
                # Use maximum multiplier to prevent double-penalizing
                max_multiplier = max(max_multiplier, rule.multiplier)
        
        modifier *= max_multiplier
        
        # Clamp to valid range
        return min(max(modifier, 0.0), 1.0)
    
    def get_all_profiles(self) -> List[SignRiskProfile]:
        """Get all registered sign profiles."""
        return list(self._profiles.values())
    
    def get_profiles_by_category(self, category: SignRiskCategory) -> List[SignRiskProfile]:
        """Get all profiles in a given risk category."""
        return [p for p in self._profiles.values() if p.risk_category == category]
    
    @property
    def num_classes(self) -> int:
        """Total number of registered sign classes."""
        return len(self._profiles)
    
    def validate(self) -> List[str]:
        """
        Validate ontology completeness and consistency.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Check all 122 classes are registered
        for cid in range(122):
            if cid not in self._profiles:
                errors.append(f"Missing class_id {cid}")
        
        # Check modifier bounds
        for cid, profile in self._profiles.items():
            if not (0.0 <= profile.base_risk_modifier <= 1.0):
                errors.append(
                    f"Class {cid} ({profile.class_name}): "
                    f"base_risk_modifier {profile.base_risk_modifier} out of [0, 1]"
                )
            if profile.relevance_duration_s <= 0:
                errors.append(
                    f"Class {cid} ({profile.class_name}): "
                    f"relevance_duration_s must be positive"
                )
        
        return errors
