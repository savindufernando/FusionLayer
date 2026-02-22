import type { WeatherScenario } from '../types';
import { MapPin, Camera, Zap, Cloud, Sun, CloudRain, CloudFog, Moon, CloudLightning } from 'lucide-react';

interface ControlsProps {
    isTracking: boolean;
    isFusing: boolean;
    weather: WeatherScenario;
    gpsPermission: 'prompt' | 'granted' | 'denied' | 'unavailable';
    cameraActive: boolean;
    gpsError: string | null;
    cameraError: string | null;
    tickCount: number;
    onStartTracking: () => void;
    onStopTracking: () => void;
    onWeatherChange: (w: WeatherScenario) => void;
    onReset: () => void;
    onDownloadReport?: () => void;
    onExportJSON?: () => void;
    hasTripData?: boolean;
    onShowHistory?: () => void;
}

export default function Controls({
    isTracking,
    isFusing,
    weather,
    gpsPermission,
    cameraActive,
    gpsError,
    cameraError,
    tickCount,
    onStartTracking,
    onStopTracking,
    onWeatherChange,
    onReset,
    onDownloadReport,
    onExportJSON,
    hasTripData,
    onShowHistory,
}: ControlsProps) {
    return (
        <div className="card controls-card">
            <div className="card-header">
                <h2 className="card-title">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="3" />
                        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
                    </svg>
                    Controls
                </h2>
            </div>
            <div className="controls-content">
                {/* Start / Stop Tracking */}
                <div className="controls-row">
                    {!isTracking ? (
                        <button className="btn btn-primary" onClick={onStartTracking}>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                                <circle cx="12" cy="10" r="3" />
                            </svg>
                            Start Tracking
                        </button>
                    ) : (
                        <button className="btn btn-warning" onClick={onStopTracking}>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                                <rect x="6" y="4" width="4" height="16" />
                                <rect x="14" y="4" width="4" height="16" />
                            </svg>
                            Stop
                        </button>
                    )}
                    <button className="btn btn-outline" onClick={onReset}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M1 4v6h6" />
                            <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
                        </svg>
                        Reset
                    </button>
                </div>

                {/* Report Download */}
                {!isTracking && hasTripData && (
                    <div className="controls-row" style={{ marginTop: '0.5rem', gap: '0.5rem' }}>
                        <button className="btn btn-success" onClick={onDownloadReport} style={{ flex: 1, background: '#4f46e5', borderColor: '#4f46e5' }}>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                                <polyline points="14 2 14 8 20 8" />
                                <line x1="16" y1="13" x2="8" y2="13" />
                                <line x1="16" y1="17" x2="8" y2="17" />
                                <polyline points="10 9 9 9 8 9" />
                            </svg>
                            Report <span className="kbd-hint">D</span>
                        </button>
                        <button className="btn btn-outline" onClick={onExportJSON} style={{ flex: 1, borderColor: 'var(--border-color)', color: 'var(--text-secondary)' }}>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                                <polyline points="7 10 12 15 17 10" />
                                <line x1="12" y1="15" x2="12" y2="3" />
                            </svg>
                            Export JSON
                        </button>
                    </div>
                )}

                {/* History Button */}
                <div className="controls-row" style={{ marginTop: '0.5rem' }}>
                    <button className="btn btn-outline" onClick={onShowHistory} style={{ width: '100%', borderColor: 'var(--border-color)', color: 'var(--text-secondary)' }}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '8px' }}>
                            <circle cx="12" cy="12" r="10"></circle>
                            <polyline points="12 6 12 12 16 14"></polyline>
                        </svg>
                        Driver History
                    </button>
                </div>

                {/* System Status */}
                <div className="module-status-grid">
                    <div className={`module-status-item ${gpsPermission === 'granted' ? 'active' : gpsPermission === 'denied' ? 'error' : ''}`}>
                        <span className="module-status-icon"><MapPin size={16} /></span>
                        <div className="module-status-info">
                            <span className="module-status-name">GPS</span>
                            <span className="module-status-state">
                                {gpsPermission === 'granted' ? 'Active' :
                                    gpsPermission === 'denied' ? 'Denied' :
                                        gpsPermission === 'unavailable' ? 'Unavailable' :
                                            'Ready'}
                            </span>
                        </div>
                    </div>
                    <div className={`module-status-item ${cameraActive ? 'active' : cameraError ? 'error' : ''}`}>
                        <span className="module-status-icon"><Camera size={16} /></span>
                        <div className="module-status-info">
                            <span className="module-status-name">Camera</span>
                            <span className="module-status-state">
                                {cameraActive ? 'Active' : cameraError ? 'Error' : 'Ready'}
                            </span>
                        </div>
                    </div>
                    <div className={`module-status-item ${isFusing ? 'active' : ''}`}>
                        <span className="module-status-icon"><Zap size={16} /></span>
                        <div className="module-status-info">
                            <span className="module-status-name">Fusion</span>
                            <span className="module-status-state">
                                {isFusing ? `${tickCount} cycles` : 'Idle'}
                            </span>
                        </div>
                    </div>
                </div>

                {/* Weather Override */}
                <div className="control-group">
                    <label className="control-label">Weather Scenario</label>
                    <div className="weather-pills">
                        {([
                            { val: 'realtime' as WeatherScenario, icon: <Cloud size={14} />, label: 'Real-Time' },
                            { val: 'sunny' as WeatherScenario, icon: <Sun size={14} />, label: 'Sunny' },
                            { val: 'rain' as WeatherScenario, icon: <CloudRain size={14} />, label: 'Rain' },
                            { val: 'fog' as WeatherScenario, icon: <CloudFog size={14} />, label: 'Fog' },
                            { val: 'night' as WeatherScenario, icon: <Moon size={14} />, label: 'Night' },
                            { val: 'storm' as WeatherScenario, icon: <CloudLightning size={14} />, label: 'Storm' },
                        ]).map(w => (
                            <button
                                key={w.val}
                                className={`weather-pill ${weather === w.val ? 'active' : ''}`}
                                onClick={() => onWeatherChange(w.val)}
                            >
                                {w.icon} {w.label}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Errors */}
                {gpsError && (
                    <div className="control-error">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" />
                            <line x1="12" y1="8" x2="12" y2="12" />
                            <line x1="12" y1="16" x2="12.01" y2="16" />
                        </svg>
                        {gpsError}
                    </div>
                )}
                {cameraError && (
                    <div className="control-error">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" />
                            <line x1="12" y1="8" x2="12" y2="12" />
                            <line x1="12" y1="16" x2="12.01" y2="16" />
                        </svg>
                        {cameraError}
                    </div>
                )}
            </div>
        </div>
    );
}
