import { useState, useRef, useCallback, useEffect } from 'react';
import type { VehicleState, WeatherScenario, FusedPredictionResponse, AutoPredictRequest } from '../types';
import { autoPredict } from '../services/api';
import { useWebSocket } from './useWebSocket';



export interface TrailPoint {
    lat: number;
    lng: number;
    risk: number;
    level: 'LOW' | 'MEDIUM' | 'HIGH';
}

export interface TripStats {
    startTime: number | null;
    endTime: number | null;
    distanceKm: number;
    maxRisk: number;
    avgRisk: number;
    riskSamples: number;
    highRiskEvents: {
        time: number;
        lat: number;
        lng: number;
        risk: number;
        description: string;
    }[];
}

export interface RealTimeState {
    fusionResult: FusedPredictionResponse | null;
    trail: TrailPoint[];
    fullHistory: TrailPoint[];
    tripStats: TripStats;
    isRunning: boolean;
    error: string | null;
    tickCount: number;
    lastUpdate: number | null;
    isWebSocket: boolean;
}

/**
 * Real-time fusion hook.
 * Takes live GPS data + dashcam frame capture function,
 * calls the real /api/fused-predict/auto endpoint periodically.
 */
export function useRealTimeFusion(
    vehicle: VehicleState,
    captureFrame: () => string | null,
    weather: WeatherScenario,
) {
    // ─── WebSocket Integration ───────────────────────────────────
    const { lastMessage, isConnected } = useWebSocket<FusedPredictionResponse>('/api/fusion/ws');

    const [state, setState] = useState<RealTimeState>({
        fusionResult: null,
        trail: [],
        fullHistory: [],
        tripStats: {
            startTime: null,
            endTime: null,
            distanceKm: 0,
            maxRisk: 0,
            avgRisk: 0,
            riskSamples: 0,
            highRiskEvents: [],
        },
        isRunning: false,
        error: null,
        tickCount: 0,
        lastUpdate: null,
        isWebSocket: false,
    });

    const intervalRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const vehicleRef = useRef(vehicle);
    const weatherRef = useRef(weather);
    const captureRef = useRef(captureFrame);

    vehicleRef.current = vehicle;
    weatherRef.current = weather;
    captureRef.current = captureFrame;

    // Sync isWebSocket flag
    useEffect(() => {
        setState(prev => ({ ...prev, isWebSocket: isConnected }));
    }, [isConnected]);

    // Handle incoming WebSocket messages
    useEffect(() => {
        if (lastMessage && state.isRunning) {
            updateStateWithResult(lastMessage, vehicleRef.current);
        }
    }, [lastMessage]);

    const getDynamicInterval = useCallback((speed: number): number => {
        if (speed > 70) return 400;   // Highway: ~2.5 scans/sec
        if (speed > 30) return 800;   // City: ~1.2 scans/sec
        return 1500;                  // Stationary/Slow: ~0.6 scans/sec
    }, []);

    const updateStateWithResult = useCallback((result: FusedPredictionResponse, v: VehicleState) => {
        const newTrailPoint: TrailPoint = {
            lat: v.lat,
            lng: v.lng,
            risk: result.fused_risk_score,
            level: result.fused_risk_level,
        };

        setState(prev => {
            // Calculate distance from last point
            let dist = 0;
            if (prev.fullHistory.length > 0) {
                const last = prev.fullHistory[prev.fullHistory.length - 1];
                dist = calcDistance(last.lat, last.lng, v.lat, v.lng);
            }

            const newMaxRisk = Math.max(prev.tripStats.maxRisk, result.fused_risk_score);
            const newAvgRisk = ((prev.tripStats.avgRisk * prev.tripStats.riskSamples) + result.fused_risk_score) / (prev.tripStats.riskSamples + 1);

            const newEvents = [...prev.tripStats.highRiskEvents];
            if (result.fused_risk_level === 'HIGH' || result.fused_risk_score > 60) {
                const lastEvent = newEvents.length > 0 ? newEvents[newEvents.length - 1] : null;
                const timeSinceLast = lastEvent ? Date.now() - lastEvent.time : 99999;
                if (timeSinceLast > 10000) {
                    newEvents.push({
                        time: Date.now(),
                        lat: v.lat,
                        lng: v.lng,
                        risk: result.fused_risk_score,
                        description: result.fusion_reasons[0]?.description || 'High Risk detected',
                    });
                }
            }

            return {
                ...prev,
                fusionResult: result,
                trail: [...prev.trail.slice(-100), newTrailPoint],
                fullHistory: [...prev.fullHistory, newTrailPoint],
                tripStats: {
                    ...prev.tripStats,
                    distanceKm: prev.tripStats.distanceKm + dist,
                    maxRisk: newMaxRisk,
                    avgRisk: newAvgRisk,
                    riskSamples: prev.tripStats.riskSamples + 1,
                    highRiskEvents: newEvents,
                },
                error: null,
                tickCount: prev.tickCount + 1,
                lastUpdate: Date.now(),
            };
        });
    }, []);

    const isRunningRef = useRef(false);

    const tick = useCallback(async () => {
        if (!isRunningRef.current) return;

        const v = vehicleRef.current;
        if (v.lat === 0 && v.lng === 0) {
            // Reschedule if no GPS yet
            intervalRef.current = setTimeout(tick, 1000);
            return;
        }

        const frame = captureRef.current();
        const request: AutoPredictRequest = {
            latitude: v.lat,
            longitude: v.lng,
            heading: v.heading,
            speed_kph: v.speed,
            scenario: weatherRef.current,
            image_base64: frame || undefined,
        };

        try {
            console.log(`[Fusion] Tick ${state.tickCount + 1}: Requesting prediction...`);
            const result = await autoPredict(request);
            console.log(`[Fusion] Result received:`, result);

            // Always update state from the direct response for immediate feedback
            updateStateWithResult(result, v);
        } catch (err) {
            console.error(`[Fusion] Loop error:`, err);
            setState(prev => ({
                ...prev,
                error: (err as Error).message,
                tickCount: prev.tickCount + 1,
            }));
        }

        // Schedule next tick based on current speed
        const nextInterval = getDynamicInterval(v.speed);
        intervalRef.current = setTimeout(tick, nextInterval);
    }, [isConnected, updateStateWithResult, getDynamicInterval, state.isRunning]);

    const start = useCallback(() => {
        if (intervalRef.current) return;
        isRunningRef.current = true;
        setState(prev => ({
            ...prev,
            isRunning: true,
            error: null,
            tripStats: { ...prev.tripStats, startTime: Date.now() }
        }));

        // Use a timeout to kick off the loop instead of setInterval
        const bootstrapTick = async () => {
            await tick();
        };
        bootstrapTick();
    }, [tick]);

    const stop = useCallback(() => {
        isRunningRef.current = false;
        if (intervalRef.current) {
            clearTimeout(intervalRef.current);
            intervalRef.current = null;
        }
        setState(prev => ({
            ...prev,
            isRunning: false,
            tripStats: { ...prev.tripStats, endTime: Date.now() }
        }));
    }, []);

    const clearTrail = useCallback(() => {
        setState(prev => ({
            ...prev,
            trail: [],
            fullHistory: [],
            fusionResult: null,
            tickCount: 0,
            tripStats: {
                startTime: null,
                endTime: null,
                distanceKm: 0,
                maxRisk: 0,
                avgRisk: 0,
                riskSamples: 0,
                highRiskEvents: [],
            }
        }));
    }, []);

    function calcDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
        const R = 6371; // km
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLon = (lon2 - lon1) * Math.PI / 180;
        const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }

    useEffect(() => {
        return () => {
            if (intervalRef.current) clearTimeout(intervalRef.current);
        };
    }, []);

    return { state, start, stop, clearTrail };
}
