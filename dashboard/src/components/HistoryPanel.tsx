import { useEffect, useState } from 'react';
import { getDriverProfile, getTrips } from '../services/api';
import type { TripResponse, DriverProfileResponse } from '../types';
import { TrendingUp } from 'lucide-react';

export default function HistoryPanel({ onClose }: { onClose: () => void }) {
    const [profile, setProfile] = useState<DriverProfileResponse | null>(null);
    const [trips, setTrips] = useState<TripResponse[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const load = async () => {
            try {
                const [p, t] = await Promise.all([getDriverProfile(), getTrips()]);
                setProfile(p);
                setTrips(t);
            } catch (e) {
                console.error(e);
            } finally {
                setLoading(false);
            }
        };
        load();
    }, []);

    return (
        <div className="overlay-backdrop" onClick={onClose}>
            <div className="card history-card animate-in" onClick={e => e.stopPropagation()}>
                <div className="card-header history-header">
                    <h2>Driver Safety Profile <TrendingUp size={16} style={{ display: 'inline', verticalAlign: 'middle' }} /></h2>
                    <button className="btn-close" onClick={onClose}>×</button>
                </div>

                {loading ? <div className="loading" style={{ padding: '2rem', textAlign: 'center' }}>Loading History...</div> : (
                    <div className="history-content">
                        {/* Profile Stats */}
                        {profile && (
                            <div className="stats-dashboard">
                                <div className="stat-box safety-score">
                                    <div className="stat-label">Safety Index</div>
                                    <div className="stat-val" style={{ color: profile.avg_safety_score >= 80 ? '#22c55e' : '#eab308' }}>
                                        {profile.avg_safety_score.toFixed(1)}
                                    </div>
                                    <div className="stat-sub">/ 100</div>
                                </div>
                                <div className="stat-box">
                                    <div className="stat-label">Total Distance</div>
                                    <div className="stat-val">{profile.total_distance_km.toFixed(1)}</div>
                                    <div className="stat-sub">km</div>
                                </div>
                                <div className="stat-box">
                                    <div className="stat-label">Total Trips</div>
                                    <div className="stat-val">{profile.total_trips}</div>
                                    <div className="stat-sub">sessions</div>
                                </div>
                            </div>
                        )}

                        {/* Recent Trips Table */}
                        <h3 style={{ marginTop: '1.5rem', marginBottom: '0.5rem', fontSize: '1.1rem' }}>Recent Trips</h3>
                        <div className="trip-table-container">
                            <table className="trip-table">
                                <thead>
                                    <tr>
                                        <th>Date</th>
                                        <th>Duration</th>
                                        <th>Dist (km)</th>
                                        <th>Score</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {trips.length === 0 ? (
                                        <tr><td colSpan={4} style={{ textAlign: 'center', padding: '1rem' }}>No trips recorded yet.</td></tr>
                                    ) : trips.map(t => (
                                        <tr key={t.id}>
                                            <td>
                                                <div style={{ fontWeight: 500 }}>{new Date(t.start_time).toLocaleDateString()}</div>
                                                <div style={{ fontSize: '0.8em', color: 'var(--text-tertiary)' }}>{new Date(t.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
                                            </td>
                                            <td>{Math.floor(t.duration_seconds / 60)}m {t.duration_seconds % 60}s</td>
                                            <td>{t.distance_km.toFixed(1)}</td>
                                            <td>
                                                <span className={`score-badge ${t.safety_score >= 80 ? 'good' : t.safety_score >= 60 ? 'avg' : 'bad'}`}>
                                                    {t.safety_score.toFixed(0)}
                                                </span>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
