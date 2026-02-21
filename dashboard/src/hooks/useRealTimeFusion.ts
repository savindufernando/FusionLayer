import { useState, useRef, useCallback, useEffect } from 'react';
import type { VehicleState, WeatherScenario, FusedPredictionResponse, AutoPredictRequest } from '../types';
import { autoPredict } from '../services/api';

const POLL_INTERVAL = 2000; // Send data to API every 2 seconds

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
    });

    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const vehicleRef = useRef(vehicle);
    const weatherRef = useRef(weather);
    const captureRef = useRef(captureFrame);

    vehicleRef.current = vehicle;
    weatherRef.current = weather;
    captureRef.current = captureFrame;

    const tick = useCallback(async () => {
        const v = vehicleRef.current;

        // Don't send if no GPS position yet
        if (v.lat === 0 && v.lng === 0) return;

        // Capture camera frame
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
            const result = await autoPredict(request);

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

                // Update basic stats
                const newMaxRisk = Math.max(prev.tripStats.maxRisk, result.fused_risk_score);
                const newAvgRisk = ((prev.tripStats.avgRisk * prev.tripStats.riskSamples) + result.fused_risk_score) / (prev.tripStats.riskSamples + 1);

                // Track high risk events (cooldown 10s roughly checked by distance/time or simplified)
                // specific logic: if high risk and far enough from last event
                const newEvents = [...prev.tripStats.highRiskEvents];
                if (result.fused_risk_level === 'HIGH' || result.fused_risk_score > 60) {
                    const lastEvent = newEvents.length > 0 ? newEvents[newEvents.length - 1] : null;
                    const timeSinceLast = lastEvent ? Date.now() - lastEvent.time : 99999;

                    if (timeSinceLast > 10000) { // 10s cooldown to avoid spam
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
        } catch (err) {
            setState(prev => ({
                ...prev,
                error: (err as Error).message,
                tickCount: prev.tickCount + 1,
            }));
        }
    }, []);

    const start = useCallback(() => {
        if (intervalRef.current) return;
        setState(prev => ({
            ...prev,
            isRunning: true,
            error: null,
            tripStats: { ...prev.tripStats, startTime: Date.now() } // Set start time
        }));
        tick();
        intervalRef.current = setInterval(tick, POLL_INTERVAL);
    }, [tick]);

    const stop = useCallback(() => {
        if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
        }
        setState(prev => ({
            ...prev,
            isRunning: false,
            tripStats: { ...prev.tripStats, endTime: Date.now() } // Set end time
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
            if (intervalRef.current) clearInterval(intervalRef.current);
        };
    }, []);

    return { state, start, stop, clearTrail };
}
