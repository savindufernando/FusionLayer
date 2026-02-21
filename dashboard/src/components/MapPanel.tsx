import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { Hotspot } from '../types';
import { fetchHotspots } from '../services/api';

interface TrailPoint {
    lat: number;
    lng: number;
    risk: number;
    level: 'LOW' | 'MEDIUM' | 'HIGH';
}

interface MapPanelProps {
    lat: number;
    lng: number;
    heading: number;
    trail: TrailPoint[];
    isMoving: boolean;
}

// Default center (Colombo, Sri Lanka) when GPS hasn't acquired a fix yet
const DEFAULT_LAT = 6.9271;
const DEFAULT_LNG = 79.8612;
const DEFAULT_ZOOM = 14;

const RISK_COLORS: Record<string, string> = {
    LOW: '#16a34a',
    MEDIUM: '#ca8a04',
    HIGH: '#dc2626',
};

export default function MapPanel({ lat, lng, heading, trail, isMoving: _isMoving }: MapPanelProps) {
    const mapRef = useRef<L.Map | null>(null);
    const markerRef = useRef<L.Marker | null>(null);
    const trailLayerRef = useRef<L.LayerGroup | null>(null);
    const hotspotLayerRef = useRef<L.LayerGroup | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const hasReceivedGPS = useRef(false);
    const [hotspots, setHotspots] = useState<Hotspot[]>([]);

    // Determine display coordinates — use defaults if no GPS fix yet
    const displayLat = (lat === 0 && lng === 0) ? DEFAULT_LAT : lat;
    const displayLng = (lat === 0 && lng === 0) ? DEFAULT_LNG : lng;
    const hasGPS = lat !== 0 || lng !== 0;

    // Fetch hotspots on mount
    useEffect(() => {
        fetchHotspots()
            .then(res => setHotspots(res.hotspots))
            .catch(() => {
                // Fallback: use known Colombo hotspots if DZ module is offline
                setHotspots([
                    { id: 1, name: 'Borella Junction', latitude: 6.9147, longitude: 79.8775, report_count: 10, risk_boost: 0.40 },
                    { id: 2, name: 'Bambalapitiya Junction', latitude: 6.9080, longitude: 79.8535, report_count: 8, risk_boost: 0.25 },
                    { id: 3, name: 'Dehiwala Junction', latitude: 6.8549, longitude: 79.8650, report_count: 12, risk_boost: 0.35 },
                    { id: 4, name: 'Nugegoda Junction', latitude: 6.8723, longitude: 79.8888, report_count: 7, risk_boost: 0.30 },
                    { id: 5, name: 'Rajagiriya Junction', latitude: 6.9067, longitude: 79.8960, report_count: 9, risk_boost: 0.28 },
                    { id: 6, name: 'Kirulapone Junction', latitude: 6.8815, longitude: 79.8658, report_count: 6, risk_boost: 0.22 },
                    { id: 7, name: 'Kaduwela Junction', latitude: 6.9306, longitude: 79.9830, report_count: 11, risk_boost: 0.38 },
                    { id: 8, name: 'Maharagama Junction', latitude: 6.8467, longitude: 79.9281, report_count: 8, risk_boost: 0.32 },
                ]);
            });
    }, []);

    // Initialize map
    useEffect(() => {
        if (!containerRef.current || mapRef.current) return;

        const map = L.map(containerRef.current, {
            center: [DEFAULT_LAT, DEFAULT_LNG],
            zoom: DEFAULT_ZOOM,
            zoomControl: true,
            attributionControl: true,
        });

        // OpenStreetMap tiles
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '© OpenStreetMap',
        }).addTo(map);

        // Vehicle marker
        const carIcon = L.divIcon({
            className: 'car-marker',
            html: `<div class="car-marker-inner" style="transform: rotate(${heading}deg)">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="#4f46e5">
          <path d="M12 2L4 20h16L12 2z"/>
        </svg>
      </div>`,
            iconSize: [28, 28],
            iconAnchor: [14, 14],
        });

        const marker = L.marker([DEFAULT_LAT, DEFAULT_LNG], { icon: carIcon }).addTo(map);
        const trailLayer = L.layerGroup().addTo(map);
        const hotspotLayer = L.layerGroup().addTo(map);

        mapRef.current = map;
        markerRef.current = marker;
        trailLayerRef.current = trailLayer;
        hotspotLayerRef.current = hotspotLayer;

        // Force a resize after render to fix tile rendering
        setTimeout(() => {
            map.invalidateSize();
        }, 200);

        return () => {
            map.remove();
            mapRef.current = null;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Draw hotspot markers
    useEffect(() => {
        if (!hotspotLayerRef.current) return;
        hotspotLayerRef.current.clearLayers();

        for (const h of hotspots) {
            // Black circle with pulsing ring for each accident hotspot
            const hotspotIcon = L.divIcon({
                className: 'hotspot-marker',
                html: `<div class="hotspot-marker-inner">
          <div class="hotspot-pulse"></div>
          <div class="hotspot-dot"></div>
        </div>`,
                iconSize: [24, 24],
                iconAnchor: [12, 12],
            });

            const m = L.marker([h.latitude, h.longitude], { icon: hotspotIcon });
            m.bindPopup(`
        <div style="font-family: Inter, sans-serif; min-width: 180px;">
          <b style="font-size: 13px;">⚠️ ${h.name}</b><br/>
          <span style="font-size: 11px; color: #64748b;">Accident Black Spot</span>
          <hr style="margin: 6px 0; border: none; border-top: 1px solid #e2e8f0;" />
          <div style="font-size: 12px;">
            <b>${h.report_count}</b> reported incidents<br/>
            Risk boost: <b style="color: #dc2626;">+${(h.risk_boost * 100).toFixed(0)}%</b>
          </div>
        </div>
      `);
            m.addTo(hotspotLayerRef.current!);
        }
    }, [hotspots]);

    // Update marker position when GPS sends data
    useEffect(() => {
        if (!markerRef.current || !mapRef.current) return;

        markerRef.current.setLatLng([displayLat, displayLng]);

        // Update icon rotation & color
        const carIcon = L.divIcon({
            className: 'car-marker',
            html: `<div class="car-marker-inner" style="transform: rotate(${heading}deg)">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="${hasGPS ? '#4f46e5' : '#94a3b8'}">
          <path d="M12 2L4 20h16L12 2z"/>
        </svg>
      </div>`,
            iconSize: [28, 28],
            iconAnchor: [14, 14],
        });
        markerRef.current.setIcon(carIcon);

        // When we first get a real GPS fix, fly to that location
        if (hasGPS && !hasReceivedGPS.current) {
            hasReceivedGPS.current = true;
            mapRef.current.flyTo([displayLat, displayLng], 16, { duration: 1.5 });
        } else if (hasGPS) {
            mapRef.current.panTo([displayLat, displayLng], { animate: true, duration: 0.5 });
        }
    }, [displayLat, displayLng, heading, hasGPS]);

    // Update trail
    useEffect(() => {
        if (!trailLayerRef.current) return;
        trailLayerRef.current.clearLayers();

        for (let i = 1; i < trail.length; i++) {
            const prev = trail[i - 1];
            const curr = trail[i];
            L.polyline(
                [[prev.lat, prev.lng], [curr.lat, curr.lng]],
                {
                    color: RISK_COLORS[curr.level] || '#94a3b8',
                    weight: 4,
                    opacity: Math.max(0.3, 1 - (trail.length - i) * 0.015),
                }
            ).addTo(trailLayerRef.current!);
        }

        if (trail.length > 0) {
            const last = trail[trail.length - 1];
            L.circleMarker([last.lat, last.lng], {
                radius: 5,
                fillColor: RISK_COLORS[last.level],
                fillOpacity: 0.8,
                color: '#fff',
                weight: 2,
            }).addTo(trailLayerRef.current!);
        }
    }, [trail]);

    return (
        <div className="card map-card">
            <div className="card-header">
                <h2 className="card-title">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                        <circle cx="12" cy="10" r="3" />
                    </svg>
                    Live Map
                </h2>
                <div className="map-header-right">
                    <span className="hotspot-count-badge">⚫ {hotspots.length} Black Spots</span>
                    <span className="coord-badge">
                        {hasGPS ? `${displayLat.toFixed(4)}, ${displayLng.toFixed(4)}` : 'Waiting for GPS...'}
                    </span>
                </div>
            </div>
            <div ref={containerRef} className="map-container" />
            <div className="map-legend">
                <span className="legend-item"><span className="legend-dot" style={{ background: '#16a34a' }} />Low Risk</span>
                <span className="legend-item"><span className="legend-dot" style={{ background: '#ca8a04' }} />Medium</span>
                <span className="legend-item"><span className="legend-dot" style={{ background: '#dc2626' }} />High Risk</span>
                <span className="legend-item"><span className="legend-dot hotspot-legend-dot" />Black Spot</span>
            </div>
        </div>
    );
}
