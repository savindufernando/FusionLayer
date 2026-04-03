import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { Hotspot } from '../types';
import { fetchHotspots, fetchHazards } from '../services/api';

interface RoutePlanResponse {
    success: boolean;
    coordinates: number[][]; // [lat, lng]
    instructions: { road: string; instruction: string }[];
    distance_m: number;
}

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
    const [hazards, setHazards] = useState<any[]>([]);
    
    // Navigation State
    const [navigationRoute, setNavigationRoute] = useState<number[][] | null>(null);
    const [smoothRoute, setSmoothRoute] = useState<number[][] | null>(null);
    const [navDetails, setNavDetails] = useState<{distance: number, instructions: any[]}>({ distance: 0, instructions: [] });
    const [isNavMode, setIsNavMode] = useState<boolean>(false);
    const navModeRef = useRef<boolean>(false);
    const routeLayerRef = useRef<L.LayerGroup | null>(null);

    // Search State
    const [searchQuery, setSearchQuery] = useState("");
    const [searchResults, setSearchResults] = useState<any[]>([]);
    const [isSearching, setIsSearching] = useState(false);

    // Determine display coordinates — use defaults if no GPS fix yet
    const displayLat = (lat === 0 && lng === 0) ? DEFAULT_LAT : lat;
    const displayLng = (lat === 0 && lng === 0) ? DEFAULT_LNG : lng;
    const hasGPS = lat !== 0 || lng !== 0;

    // Fetch hotspots and hazards on mount
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

        fetchHazards()
            .then(res => setHazards(res.hazards || []))
            .catch(err => console.error("Could not fetch hazards:", err));
    }, []);

    // Initialize map
    useEffect(() => {
        if (!containerRef.current || mapRef.current) return;

        const map = L.map(containerRef.current, {
            center: [DEFAULT_LAT, DEFAULT_LNG],
            zoom: DEFAULT_ZOOM,
            zoomControl: true,
            attributionControl: true,
            doubleClickZoom: true,
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
        const routeLayer = L.layerGroup().addTo(map);

        mapRef.current = map;
        markerRef.current = marker;
        trailLayerRef.current = trailLayer;
        hotspotLayerRef.current = hotspotLayer;
        routeLayerRef.current = routeLayer;

        map.on('click', async (e) => {
            if (!navModeRef.current) return;
            triggerNavigationToDest(e.latlng.lat, e.latlng.lng);
        });

        setTimeout(() => {
            map.invalidateSize();
        }, 200);

        return () => {
            map.remove();
            mapRef.current = null;
        };
    }, []);

    const triggerNavigationToDest = async (destLat: number, destLng: number) => {
        let startLat = DEFAULT_LAT;
        let startLng = DEFAULT_LNG;
        if (markerRef.current) {
            const pos = markerRef.current.getLatLng();
            startLat = pos.lat;
            startLng = pos.lng;
        }

        try {
            const API_KEY = import.meta.env.VITE_DG_API_KEY || 'dg-fusion-dev-key-2026';
            const res = await fetch(`/api/navigation/plan?start_lat=${startLat}&start_lon=${startLng}&end_lat=${destLat}&end_lon=${destLng}&safety_weight=0.8`, {
                headers: { 'X-API-Key': API_KEY }
            });
            
            if (res.ok) {
                const data: RoutePlanResponse = await res.json();
                if (data.success) {
                    setNavigationRoute(data.coordinates);
                    setNavDetails({ distance: data.distance_m, instructions: data.instructions });
                    setIsNavMode(false);
                    navModeRef.current = false;

                    if (mapRef.current) {
                        mapRef.current.flyTo([destLat, destLng], 15);
                    }
                    return; // Success, we are done!
                }
            } 
            
            // If backend fails (e.g. outside Colombo db bounds), fallback to 100% Free Nationwide OSRM Routing!
            console.log("Safe-Route not possible or out of bounds. Falling back to Nationwide Fast Route.");
            const osrmUrl = `https://router.project-osrm.org/route/v1/driving/${startLng},${startLat};${destLng},${destLat}?overview=full&geometries=geojson`;
            const osrmRes = await fetch(osrmUrl);
            const osrmData = await osrmRes.json();
            
            if (osrmData.code === 'Ok' && osrmData.routes.length > 0) {
                const geo = osrmData.routes[0].geometry.coordinates;
                const latLngGeo = geo.map((c: number[]) => [c[1], c[0]]);
                
                // Directly set the smooth route (bypassing backend constraints!)
                setNavigationRoute([]); // Clear backend state
                setSmoothRoute(latLngGeo);
                setNavDetails({ 
                    distance: osrmData.routes[0].distance, 
                    instructions: [{ road: "Nationwide Route", instruction: "Follow the highlighted path." }] 
                });
                
                setIsNavMode(false);
                navModeRef.current = false;
                if (mapRef.current) {
                    mapRef.current.flyTo([destLat, destLng], 13);
                }
            } else {
                alert("Could not find any road route to that location (even with Nationwide fallback).");
            }
            
        } catch (err) {
            console.error("Navigation error:", err);
            alert("Navigation network error.");
        }
    };

    useEffect(() => {
        if (!searchQuery || searchQuery.trim().length < 3) {
            setSearchResults([]);
            return;
        }

        const delayDebounceFn = setTimeout(async () => {
            setIsSearching(true);
            try {
                const response = await fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(searchQuery)}&format=json&addressdetails=1&limit=5&countrycodes=LK`);
                const data = await response.json();
                setSearchResults(data);
            } catch (err) {
                console.error("Search error:", err);
            } finally {
                setIsSearching(false);
            }
        }, 500);

        return () => clearTimeout(delayDebounceFn);
    }, [searchQuery]);

    useEffect(() => {
        if (!hotspotLayerRef.current) return;
        hotspotLayerRef.current.clearLayers();

        for (const h of hotspots) {
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
          <b style="font-size: 13px;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#dc2626" stroke-width="2" style="vertical-align: middle;"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> ${h.name}</b><br/>
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

        for (const h of hazards) {
            const hazardIcon = L.divIcon({
                className: 'hazard-marker',
                html: `<div class="hazard-marker-inner" style="background:#f59e0b; width:18px; height:18px; border-radius:50%; border:2px solid white; box-shadow:0 1px 3px rgba(0,0,0,0.5);"></div>`,
                iconSize: [18, 18],
                iconAnchor: [9, 9],
            });

            const m = L.marker([h.latitude, h.longitude], { icon: hazardIcon });
            m.bindPopup(`
        <div style="font-family: Inter, sans-serif; min-width: 150px;">
          <b style="font-size: 13px; color: #f59e0b;">Reported Hazard</b><br/>
          <span style="font-size: 12px; font-weight: bold;">Type: ${h.type || h.hazard_type}</span><br/>
          Severity: ${h.severity}/5<br/>
          <i>${h.description || ''}</i>
        </div>
      `);
            m.addTo(hotspotLayerRef.current!);
        }
    }, [hotspots, hazards]);

    useEffect(() => {
        if (!markerRef.current || !mapRef.current) return;

        markerRef.current.setLatLng([displayLat, displayLng]);

        const carIcon = L.divIcon({
            className: 'car-marker',
            html: `<div class="car-marker-inner" style="transform: rotate(${heading}deg)">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="${hasGPS ? 'var(--accent-primary)' : 'var(--text-tertiary)'}">
          <path d="M12 2L4 20h16L12 2z"/>
        </svg>
      </div>`,
            iconSize: [28, 28],
            iconAnchor: [14, 14],
        });
        markerRef.current.setIcon(carIcon);

        if (hasGPS && !hasReceivedGPS.current) {
            hasReceivedGPS.current = true;
            mapRef.current.flyTo([displayLat, displayLng], 16, { duration: 1.5 });
        } else if (hasGPS) {
            mapRef.current.panTo([displayLat, displayLng], { animate: true, duration: 0.5 });
        }
    }, [displayLat, displayLng, heading, hasGPS]);

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
    
    useEffect(() => {
        if (!navigationRoute || navigationRoute.length === 0) {
            setSmoothRoute(null);
            return;
        }

        async function fetchCurvature() {
            try {
                let waypoints = navigationRoute as number[][];
                if (waypoints.length > 8) {
                    const start = waypoints[0];
                    const mid1 = waypoints[Math.floor(waypoints.length * 0.25)];
                    const mid2 = waypoints[Math.floor(waypoints.length * 0.50)];
                    const mid3 = waypoints[Math.floor(waypoints.length * 0.75)];
                    const end = waypoints[waypoints.length - 1];
                    waypoints = [start, mid1, mid2, mid3, end];
                } else if (waypoints.length > 3) {
                    waypoints = [waypoints[0], waypoints[Math.floor(waypoints.length / 2)], waypoints[waypoints.length - 1]];
                }

                const coordsStr = waypoints.map(c => `${c[1]},${c[0]}`).join(';');
                const url = `https://router.project-osrm.org/route/v1/driving/${coordsStr}?overview=full&geometries=geojson`;
                
                const res = await fetch(url);
                const data = await res.json();
                
                if (data.code === 'Ok' && data.routes && data.routes.length > 0) {
                    const geo = data.routes[0].geometry.coordinates;
                    const latLngGeo = geo.map((c: number[]) => [c[1], c[0]]);
                    setSmoothRoute(latLngGeo);
                } else {
                    setSmoothRoute(navigationRoute);
                }
            } catch (err) {
                console.error("OSRM Curvature error:", err);
                setSmoothRoute(navigationRoute);
            }
        }
        
        setSmoothRoute(navigationRoute);
        fetchCurvature();
    }, [navigationRoute]);
    
    useEffect(() => {
        if (!routeLayerRef.current) return;
        routeLayerRef.current.clearLayers();
        
        if (smoothRoute && smoothRoute.length > 0) {
            L.polyline(smoothRoute as [number, number][], {
                color: '#0284c7',
                weight: 6,
                opacity: 0.6,
                lineCap: 'round',
                lineJoin: 'round'
            }).addTo(routeLayerRef.current);

            L.polyline(smoothRoute as [number, number][], {
                color: '#38bdf8',
                weight: 3,
                opacity: 1.0,
                lineCap: 'round',
                lineJoin: 'round'
            }).addTo(routeLayerRef.current);
            
            const startNode = smoothRoute[0];
            L.circleMarker([startNode[0], startNode[1]], { radius: 6, fillColor: '#22c55e', color: '#fff', weight: 2, fillOpacity: 1 }).addTo(routeLayerRef.current);
            
            const dest = smoothRoute[smoothRoute.length - 1];
            L.marker([dest[0], dest[1]]).addTo(routeLayerRef.current)
                .bindPopup('<b>Nav Destination</b><br/>Safe Route Calculated').openPopup();
        }
    }, [smoothRoute]);

    return (
        <div className="card map-card" style={{ position: 'relative' }}>
            <div className="map-header" style={{ display: 'flex', alignItems: 'center', padding: '12px', borderBottom: '1px solid var(--border-color)' }}>
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: 0, fontSize: '14px', fontWeight: 600 }}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                        <circle cx="12" cy="10" r="3" />
                    </svg>
                    Live Map
                </h2>

                <div style={{ position: 'relative', flexGrow: 1, maxWidth: '300px', marginLeft: '16px' }}>
                    <input 
                        type="text" 
                        placeholder="Search for places..." 
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        style={{
                            width: '100%',
                            padding: '8px 12px 8px 32px',
                            borderRadius: '24px',
                            border: '1px solid var(--border-color)',
                            background: 'var(--bg-secondary)',
                            color: 'var(--text-primary)',
                            fontSize: '13px',
                            outline: 'none',
                            boxShadow: '0 2px 4px rgba(0,0,0,0.05)'
                        }}
                    />
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2" style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)' }}>
                        <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
                    </svg>
                    {isSearching && (
                        <div style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', fontSize: '11px', color: '#64748b' }}>
                            ...
                        </div>
                    )}
                    
                    {searchResults.length > 0 && (
                        <div style={{
                            position: 'absolute',
                            top: '100%',
                            left: 0,
                            right: 0,
                            marginTop: '8px',
                            background: 'var(--bg-primary)',
                            border: '1px solid var(--border-color)',
                            borderRadius: '8px',
                            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
                            zIndex: 2000,
                            maxHeight: '200px',
                            overflowY: 'auto'
                        }}>
                            {searchResults.map((result, i) => (
                                <div 
                                    key={i}
                                    onClick={() => {
                                        setSearchQuery('');
                                        setSearchResults([]);
                                        triggerNavigationToDest(parseFloat(result.lat), parseFloat(result.lon));
                                    }}
                                    style={{
                                        padding: '10px 12px',
                                        borderBottom: i < searchResults.length - 1 ? '1px solid var(--border-color)' : 'none',
                                        cursor: 'pointer',
                                        fontSize: '12px',
                                        color: 'var(--text-primary)',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '8px'
                                    }}
                                >
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0ea5e9" strokeWidth="2" style={{ flexShrink: 0 }}>
                                        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" />
                                    </svg>
                                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                        {result.display_name}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                <div className="map-header-right" style={{ display: 'flex', alignItems: 'center', gap: '8px', marginLeft: 'auto' }}>
                    <button 
                        onClick={() => {
                            if (navigator.geolocation) {
                                navigator.geolocation.getCurrentPosition((pos) => {
                                    const { latitude, longitude } = pos.coords;
                                    if (mapRef.current && markerRef.current) {
                                        mapRef.current.flyTo([latitude, longitude], 16, { duration: 1.5 });
                                        markerRef.current.setLatLng([latitude, longitude]);
                                    }
                                }, (err) => {
                                    console.error("Geolocation error:", err);
                                    alert("Could not get your exact location. Please ensure location permissions are enabled.");
                                });
                            } else {
                                alert("Geolocation is not supported by this browser.");
                            }
                        }}
                        style={{ 
                            fontSize: '12px', 
                            background: 'var(--bg-secondary)', 
                            color: 'var(--text-primary)', 
                            padding: '4px 12px', 
                            borderRadius: '4px', 
                            border: '1px solid var(--border-color)',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            transition: 'all 0.2s',
                        }}
                        title="Find my exact location"
                    >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '6px' }}>
                            <circle cx="12" cy="12" r="10" />
                            <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
                        </svg>
                        Locate Me
                    </button>
                    <button 
                        onClick={() => {
                            const nextState = !isNavMode;
                            setIsNavMode(nextState);
                            navModeRef.current = nextState;
                            if (nextState) {
                                setNavigationRoute(null);
                            }
                        }}
                        style={{ 
                            fontSize: '12px', 
                            background: isNavMode ? '#0ea5e9' : 'rgba(14, 165, 233, 0.1)', 
                            color: isNavMode ? 'white' : '#0ea5e9', 
                            padding: '4px 12px', 
                            borderRadius: '4px', 
                            border: '1px solid rgba(14, 165, 233, 0.3)',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            transition: 'all 0.2s',
                        }}
                    >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '6px' }}>
                            <circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>
                        </svg>
                        {isNavMode ? 'Click Map to set Target...' : 'Plan Safe Route'}
                    </button>
                    <span className="hotspot-count-badge"><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#1e293b', marginRight: 6, verticalAlign: 'middle' }} /> {hotspots.length} Black Spots</span>
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
                <span className="legend-item"><span className="legend-dot" style={{ background: '#f59e0b', border: '1px solid #fff' }}/>Hazard</span>
                <span className="legend-item"><span className="legend-dot" style={{ background: '#0ea5e9', borderRadius: '0', width: '12px', height: '4px' }}/>Safe Route</span>
            </div>
            {navigationRoute && (
                <div style={{ position: 'absolute', bottom: '10px', left: '10px', right: '10px', zIndex: 1000, background: 'var(--bg-secondary)', padding: '10px', borderRadius: '8px', border: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <strong style={{ color: '#0ea5e9' }}>Safe Navigation Active</strong>
                        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Distance: {Math.round(navDetails.distance)}m</div>
                        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Next: {navDetails.instructions[0]?.instruction || 'Proceed to destination'}</div>
                    </div>
                    <button onClick={() => setNavigationRoute(null)} style={{ background: '#dc2626', color: 'white', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontSize: '12px' }}>
                        End Navigation
                    </button>
                </div>
            )}
        </div>
    );
}
