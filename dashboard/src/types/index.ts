// ─── API Types ───────────────────────────────────────────────────

// Manual fusion (fallback when DZ/TSR modules aren't running)
export interface ManualFusionRequest {
    dz_risk_score: number;
    dz_risk_level: 'LOW' | 'MEDIUM' | 'HIGH';
    dz_confidence: number;
    tsr_input?: {
        class_id: number;
        class_name: string;
        confidence: number;
    };
    hotspot_boost: number;
    hotspot_reports: number;
    weather_condition: string;
    road_surface: string;
    speed_kph: number;
}

// Auto-predict (real system — calls live DZ + TSR modules)
export interface AutoPredictRequest {
    latitude: number;
    longitude: number;
    heading: number;
    speed_kph: number;
    scenario: string;
    image_base64?: string | null;
}

export interface FusionReason {
    source: string;
    description: string;
    impact: string;
}

export interface ActiveSign {
    class_name: string;
    confidence: number;
    risk_modifier: number;
    age_seconds: number;
}

export interface FusedPredictionResponse {
    fused_risk_score: number;
    fused_risk_level: 'LOW' | 'MEDIUM' | 'HIGH';
    belief_dangerous: number;
    plausibility_dangerous: number;
    pignistic_probability: number;
    conflict_measure: number;
    uncertainty_width: number;
    fused_confidence: number;
    dz_contribution: {
        risk_score: number;
        risk_level: string;
        confidence: number;
        mass_function?: Record<string, number>;
    };
    tsr_contribution: {
        detected: boolean;
        class_name?: string;
        confidence?: number;
        risk_category?: string;
        base_modifier?: number;
        effective_modifier?: number;
        aggregate?: Record<string, unknown>;
    };
    hotspot_contribution: {
        active: boolean;
        risk_boost?: number;
        report_count?: number;
    };
    fusion_reasons: FusionReason[];
    active_signs: ActiveSign[];
    tsr_reliability: number;
    tsr_discount_reasons: string[];
    validation_status: string;
    validation_reason: string;
    timestamp: string;
    fusion_method: string;
    adaptive_weights: {
        degraded?: boolean;
        dz_circuit?: string;
        tsr_circuit?: string;
        [key: string]: any;
    };
}

export interface HealthResponse {
    status: string;
    version: string;
    ontology_classes: number;
    buffer_size: number;
    conflict_log_size: number;
    fusion_method: string;
}

// ─── Vehicle & GPS Types ─────────────────────────────────────────

export interface GPSPosition {
    lat: number;
    lng: number;
    speed: number | null;   // m/s from GPS, null if unavailable
    heading: number | null;  // degrees from GPS
    accuracy: number;        // meters
    timestamp: number;
}

export interface VehicleState {
    lat: number;
    lng: number;
    speed: number;     // km/h
    heading: number;   // degrees
    accuracy: number;  // GPS accuracy in meters
    isTracking: boolean;
}

export type WeatherScenario = 'realtime' | 'sunny' | 'rain' | 'fog' | 'night' | 'storm' | 'peak';

// ─── Hotspot / Black Spot Types ──────────────────────────────────

export interface Hotspot {
    id: number;
    name: string;
    latitude: number;
    longitude: number;
    report_count: number;
    risk_boost: number;
    created_at?: string | null;
}

export interface HotspotsResponse {
    count: number;
    hotspots: Hotspot[];
}

// ─── Trip History Models ──────────────────────────────────────

export interface TripCreate {
    start_time: string;
    end_time: string;
    duration_seconds: number;
    distance_km: number;
    max_risk: number;
    avg_risk: number;
    safety_score: number;
    start_location?: string;
    end_location?: string;
    risk_events_count: number;
}

export interface TripResponse extends TripCreate {
    id: number;
}

export interface DriverProfileResponse {
    total_trips: number;
    total_distance_km: number;
    avg_safety_score: number;
    last_trip: TripResponse | null;
}
