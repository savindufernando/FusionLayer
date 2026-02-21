import { useState, useEffect, useRef, useCallback } from 'react';
import type { VehicleState, GPSPosition } from '../types';

/**
 * Hook that uses the browser's Geolocation API to get real GPS position.
 * Calculates speed from position changes if GPS speed is unavailable.
 */
export function useGPS() {
    const [vehicle, setVehicle] = useState<VehicleState>({
        lat: 0,
        lng: 0,
        speed: 0,
        heading: 0,
        accuracy: 0,
        isTracking: false,
    });
    const [error, setError] = useState<string | null>(null);
    const [permissionState, setPermissionState] = useState<'prompt' | 'granted' | 'denied' | 'unavailable'>('prompt');

    const watchIdRef = useRef<number | null>(null);
    const prevPosRef = useRef<GPSPosition | null>(null);

    const calculateSpeed = useCallback((prev: GPSPosition, curr: GPSPosition): number => {
        // If GPS provides speed, use it (convert m/s → km/h)
        if (curr.speed !== null && curr.speed >= 0) {
            return Math.round(curr.speed * 3.6);
        }

        // Calculate from position change
        const dt = (curr.timestamp - prev.timestamp) / 1000; // seconds
        if (dt <= 0) return vehicle.speed;

        const R = 6371000; // Earth radius in meters
        const dLat = (curr.lat - prev.lat) * Math.PI / 180;
        const dLng = (curr.lng - prev.lng) * Math.PI / 180;
        const a = Math.sin(dLat / 2) ** 2 +
            Math.cos(prev.lat * Math.PI / 180) *
            Math.cos(curr.lat * Math.PI / 180) *
            Math.sin(dLng / 2) ** 2;
        const dist = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        const speedMs = dist / dt;
        return Math.round(speedMs * 3.6); // km/h
    }, [vehicle.speed]);

    const calculateHeading = useCallback((prev: GPSPosition, curr: GPSPosition): number => {
        if (curr.heading !== null && curr.heading >= 0) return Math.round(curr.heading);

        const dLng = (curr.lng - prev.lng) * Math.PI / 180;
        const y = Math.sin(dLng) * Math.cos(curr.lat * Math.PI / 180);
        const x = Math.cos(prev.lat * Math.PI / 180) * Math.sin(curr.lat * Math.PI / 180) -
            Math.sin(prev.lat * Math.PI / 180) * Math.cos(curr.lat * Math.PI / 180) * Math.cos(dLng);
        const bearing = (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
        return Math.round(bearing);
    }, []);

    const startTracking = useCallback(() => {
        if (!navigator.geolocation) {
            setError('Geolocation is not supported by this browser');
            setPermissionState('unavailable');
            return;
        }

        setError(null);
        setPermissionState('prompt');

        watchIdRef.current = navigator.geolocation.watchPosition(
            (position) => {
                const curr: GPSPosition = {
                    lat: position.coords.latitude,
                    lng: position.coords.longitude,
                    speed: position.coords.speed,
                    heading: position.coords.heading,
                    accuracy: position.coords.accuracy,
                    timestamp: position.timestamp,
                };

                const prev = prevPosRef.current;
                let speed = 0;
                let heading = 0;

                if (prev) {
                    speed = calculateSpeed(prev, curr);
                    heading = calculateHeading(prev, curr);
                }

                prevPosRef.current = curr;
                setPermissionState('granted');

                setVehicle({
                    lat: curr.lat,
                    lng: curr.lng,
                    speed,
                    heading,
                    accuracy: Math.round(curr.accuracy),
                    isTracking: true,
                });
            },
            (err) => {
                if (err.code === err.PERMISSION_DENIED) {
                    setError('Location permission denied. Please allow location access.');
                    setPermissionState('denied');
                } else if (err.code === err.POSITION_UNAVAILABLE) {
                    setError('GPS position unavailable');
                    setPermissionState('unavailable');
                } else {
                    setError(`GPS error: ${err.message}`);
                }
            },
            {
                enableHighAccuracy: true,
                maximumAge: 2000,
                timeout: 10000,
            }
        );
    }, [calculateSpeed, calculateHeading]);

    const stopTracking = useCallback(() => {
        if (watchIdRef.current !== null) {
            navigator.geolocation.clearWatch(watchIdRef.current);
            watchIdRef.current = null;
        }
        prevPosRef.current = null;
        setVehicle(prev => ({ ...prev, isTracking: false, speed: 0 }));
    }, []);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (watchIdRef.current !== null) {
                navigator.geolocation.clearWatch(watchIdRef.current);
            }
        };
    }, []);

    return { vehicle, error, permissionState, startTracking, stopTracking };
}
