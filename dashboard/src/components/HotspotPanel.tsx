import { useState, useEffect, useCallback } from 'react';
import type { Hotspot } from '../types';
import { fetchHotspots, reportAccident } from '../services/api';

interface HotspotPanelProps {
    /** Current GPS latitude (for "report here" feature) */
    currentLat: number;
    /** Current GPS longitude */
    currentLng: number;
    /** Called when user clicks a hotspot row — map should pan to it */
    onHotspotClick?: (lat: number, lng: number) => void;
}

export default function HotspotPanel({ currentLat, currentLng, onHotspotClick }: HotspotPanelProps) {
    const [hotspots, setHotspots] = useState<Hotspot[]>([]);
    const [loading, setLoading] = useState(true);
    const [reporting, setReporting] = useState(false);
    const [showReportForm, setShowReportForm] = useState(false);
    const [severity, setSeverity] = useState(2);
    const [description, setDescription] = useState('');
    const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

    // Fetch hotspots on mount + after reports
    const loadHotspots = useCallback(async () => {
        try {
            const res = await fetchHotspots();
            setHotspots(res.hotspots);
        } catch {
            // Use fallback if DZ module offline
            setHotspots([]);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadHotspots();
    }, [loadHotspots]);

    // Handle accident report submission
    const handleReport = async () => {
        if (currentLat === 0 && currentLng === 0) {
            setFeedback({ type: 'error', text: 'GPS not available — cannot report location' });
            return;
        }

        setReporting(true);
        setFeedback(null);

        try {
            await reportAccident(currentLat, currentLng, severity, description);
            setFeedback({ type: 'success', text: 'Accident reported! Location may become a permanent black spot.' });
            setShowReportForm(false);
            setDescription('');
            setSeverity(2);
            // Reload hotspots (new one may have been promoted)
            await loadHotspots();
        } catch {
            setFeedback({ type: 'error', text: 'Failed to submit report. Is the DZ module running?' });
        } finally {
            setReporting(false);
        }
    };

    const hasGPS = currentLat !== 0 || currentLng !== 0;

    return (
        <div className="card hotspot-panel">
            <div className="card-header">
                <h2 className="card-title">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                        <line x1="12" y1="9" x2="12" y2="13" />
                        <line x1="12" y1="17" x2="12.01" y2="17" />
                    </svg>
                    Accident Black Spots
                </h2>
                <span className="hotspot-badge">{hotspots.length}</span>
            </div>

            {/* ─── Report Accident Button ──────────────────────────── */}
            <div className="hotspot-actions">
                <button
                    className="btn-report-accident"
                    onClick={() => setShowReportForm(!showReportForm)}
                    disabled={!hasGPS}
                    title={hasGPS ? 'Report an accident at your current location' : 'GPS required to report'}
                >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="12" y1="8" x2="12" y2="16" />
                        <line x1="8" y1="12" x2="16" y2="12" />
                    </svg>
                    Report Accident Here
                </button>
            </div>

            {/* ─── Report Form ─────────────────────────────────────── */}
            {showReportForm && (
                <div className="report-form">
                    <div className="report-location">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                            <circle cx="12" cy="10" r="3" />
                        </svg>
                        {currentLat.toFixed(5)}, {currentLng.toFixed(5)}
                    </div>

                    <div className="report-field">
                        <label>Severity</label>
                        <div className="severity-options">
                            {[
                                { value: 1, label: 'Minor', color: '#ca8a04' },
                                { value: 2, label: 'Major', color: '#ea580c' },
                                { value: 3, label: 'Fatal', color: '#dc2626' },
                            ].map((s) => (
                                <button
                                    key={s.value}
                                    className={`severity-btn ${severity === s.value ? 'active' : ''}`}
                                    style={{ '--severity-color': s.color } as React.CSSProperties}
                                    onClick={() => setSeverity(s.value)}
                                >
                                    {s.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="report-field">
                        <label>Description (optional)</label>
                        <input
                            type="text"
                            className="report-input"
                            placeholder="e.g. Head-on collision at junction"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            maxLength={200}
                        />
                    </div>

                    <div className="report-buttons">
                        <button className="btn-submit-report" onClick={handleReport} disabled={reporting}>
                            {reporting ? 'Submitting...' : 'Submit Report'}
                        </button>
                        <button className="btn-cancel-report" onClick={() => setShowReportForm(false)}>
                            Cancel
                        </button>
                    </div>
                </div>
            )}

            {/* ─── Feedback ────────────────────────────────────────── */}
            {feedback && (
                <div className={`report-feedback ${feedback.type}`}>
                    {feedback.text}
                </div>
            )}

            {/* ─── Hotspot List ────────────────────────────────────── */}
            <div className="hotspot-list">
                {loading ? (
                    <div className="hotspot-loading">Loading hotspots...</div>
                ) : hotspots.length === 0 ? (
                    <div className="hotspot-empty">No black spots loaded</div>
                ) : (
                    hotspots.map((h) => (
                        <div
                            key={h.id}
                            className="hotspot-row"
                            onClick={() => onHotspotClick?.(h.latitude, h.longitude)}
                            title={`Click to pan map to ${h.name}`}
                        >
                            <div className="hotspot-row-icon">
                                <div className="hotspot-dot-small" />
                            </div>
                            <div className="hotspot-row-info">
                                <span className="hotspot-row-name">{h.name}</span>
                                <span className="hotspot-row-stats">
                                    {h.report_count} reports · +{(h.risk_boost * 100).toFixed(0)}% risk
                                </span>
                            </div>
                            <div className="hotspot-row-boost">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2">
                                    <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
                                    <polyline points="16 7 22 7 22 13" />
                                </svg>
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}
