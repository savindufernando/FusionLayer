import type { ManualFusionRequest, AutoPredictRequest, FusedPredictionResponse, HealthResponse, HotspotsResponse, TripCreate, TripResponse, DriverProfileResponse } from '../types';

const API_BASE = '/api';
const DZ_BASE = '/dz-api';  // proxied to DZ module port 8000

// ─── Security: inject API key into all requests ──────────────────────────
const API_KEY = import.meta.env.VITE_DG_API_KEY || 'dg-fusion-dev-key-2026';

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
    return { 'X-API-Key': API_KEY, ...extra };
}

function jsonAuth(): Record<string, string> {
    return authHeaders({ 'Content-Type': 'application/json' });
}

// ─── Resilience: Fetch with Retry & Exponential Backoff ──────────────────
async function fetchWithRetry(
    url: string,
    options: RequestInit,
    retries: number = 3,
    backoff: number = 1000
): Promise<Response> {
    try {
        const res = await fetch(url, options);
        if (res.ok) return res;

        // Only retry on server errors (5xx) or rate limits (429)
        if (retries > 0 && (res.status >= 500 || res.status === 429)) {
            await new Promise(resolve => setTimeout(resolve, backoff));
            return fetchWithRetry(url, options, retries - 1, backoff * 2);
        }
        return res;
    } catch (err) {
        if (retries > 0) {
            await new Promise(resolve => setTimeout(resolve, backoff));
            return fetchWithRetry(url, options, retries - 1, backoff * 2);
        }
        throw err;
    }
}

/**
 * Real auto-predict — sends GPS + camera frame to the fusion API,
 * which calls live DZ (port 8000) and TSR (port 8001) modules.
 */
export async function autoPredict(request: AutoPredictRequest): Promise<FusedPredictionResponse> {
    const res = await fetchWithRetry(`${API_BASE}/fused-predict/auto`, {
        method: 'POST',
        headers: jsonAuth(),
        body: JSON.stringify(request),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Auto-predict failed' }));
        throw new Error(err.detail || 'Auto-predict failed');
    }
    return res.json();
}

/**
 * Manual predict — fallback when DZ/TSR modules aren't running.
 * User provides risk inputs via sliders.
 */
export async function manualPredict(request: ManualFusionRequest): Promise<FusedPredictionResponse> {
    const res = await fetch(`${API_BASE}/fused-predict`, {
        method: 'POST',
        headers: jsonAuth(),
        body: JSON.stringify(request),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Fusion failed' }));
        throw new Error(err.detail || 'Fusion failed');
    }
    return res.json();
}

export async function checkHealth(): Promise<HealthResponse> {
    // Health checks use shorter retry to avoid blocking UI too long
    const res = await fetchWithRetry(`${API_BASE}/fusion/health`, { headers: authHeaders() }, 2, 500);
    if (!res.ok) throw new Error('API offline');
    return res.json();
}

export async function resetEngine(): Promise<void> {
    const res = await fetch(`${API_BASE}/fusion/reset`, {
        method: 'POST',
        headers: authHeaders(),
    });
    if (!res.ok) throw new Error('Reset failed');
}

/**
 * Fetch accident hotspots (black spots) from the DZ module.
 */
export async function fetchHotspots(): Promise<HotspotsResponse> {
    const res = await fetch(`${DZ_BASE}/hotspots`, { headers: authHeaders() });
    if (!res.ok) throw new Error('Failed to fetch hotspots');
    return res.json();
}

/**
 * Report an accident at the given location (crowd-sourced).
 * If enough reports accumulate, the location auto-promotes to a permanent black spot.
 */
export async function reportAccident(
    latitude: number,
    longitude: number,
    severity: number = 2,
    description: string = ''
): Promise<{ success: boolean; message: string; report_id?: number }> {
    const res = await fetch(`${DZ_BASE}/report`, {
        method: 'POST',
        headers: jsonAuth(),
        body: JSON.stringify({ latitude, longitude, severity, description }),
    });
    if (!res.ok) throw new Error('Failed to report accident');
    return res.json();
}

export const saveTrip = async (trip: TripCreate): Promise<TripResponse> => {
    try {
        const response = await fetch('/dz-api/trips', {
            method: 'POST',
            headers: jsonAuth(),
            body: JSON.stringify(trip),
        });

        if (!response.ok) {
            throw new Error(`Failed to save trip: ${response.statusText}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error saving trip:', error);
        throw error;
    }
};

export const getDriverProfile = async (): Promise<DriverProfileResponse> => {
    try {
        const response = await fetch('/dz-api/driver-profile', { headers: authHeaders() });
        if (!response.ok) {
            throw new Error(`Failed to fetch profile: ${response.statusText}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error fetching profile:', error);
        throw error;
    }
};

export const getTrips = async (): Promise<TripResponse[]> => {
    try {
        const response = await fetch('/dz-api/trips', { headers: authHeaders() });
        if (!response.ok) {
            throw new Error(`Failed to fetch trips: ${response.statusText}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error fetching trips:', error);
        throw error;
    }
};
