import type { FusedPredictionResponse } from '../types';

interface Props {
    result: FusedPredictionResponse | null;
}

export default function SystemGeolocation({ result }: Props) {
    const dz = result?.dz_contribution;

    return (
        <div className="card system-card system-geo">
            <div className="card-header">
                <div className="system-label-row">
                    <span className="system-badge geo">SYSTEM 1</span>
                    <h2 className="card-title">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" />
                            <path d="M2 12h20" />
                            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                        </svg>
                        Geolocation Risk
                    </h2>
                </div>
                <span className="system-status">
                    {dz ? `${dz.risk_level}` : 'Waiting...'}
                </span>
            </div>
            <div className="system-content">
                {dz ? (
                    <>
                        <div className="system-metrics">
                            <div className="metric-item">
                                <div className="metric-value">{dz.risk_score.toFixed(1)}</div>
                                <div className="metric-label">Risk Score</div>
                            </div>
                            <div className="metric-item">
                                <div className="metric-value">{(dz.confidence * 100).toFixed(0)}%</div>
                                <div className="metric-label">Confidence</div>
                            </div>
                            <div className="metric-item">
                                <div className={`metric-value level-${dz.risk_level.toLowerCase()}`}>
                                    {dz.risk_level}
                                </div>
                                <div className="metric-label">Level</div>
                            </div>
                        </div>
                        {dz.mass_function && (
                            <div className="mass-bar">
                                <div className="mass-segment safe" style={{ width: `${(dz.mass_function.safe || 0) * 100}%` }} title={`Safe: ${((dz.mass_function.safe || 0) * 100).toFixed(1)}%`} />
                                <div className="mass-segment uncertain" style={{ width: `${(dz.mass_function.uncertain || 0) * 100}%` }} title={`Uncertain: ${((dz.mass_function.uncertain || 0) * 100).toFixed(1)}%`} />
                                <div className="mass-segment dangerous" style={{ width: `${(dz.mass_function.dangerous || 0) * 100}%` }} title={`Dangerous: ${((dz.mass_function.dangerous || 0) * 100).toFixed(1)}%`} />
                            </div>
                        )}
                        <p className="system-description">
                            Risk assessment based on vehicle location, speed, accident patterns, and weather conditions.
                        </p>
                    </>
                ) : (
                    <p className="system-waiting">Start driving to generate geolocation risk data</p>
                )}
            </div>
        </div>
    );
}
