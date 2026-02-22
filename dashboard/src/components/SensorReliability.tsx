import type { FusedPredictionResponse } from '../types';
import { ShieldAlert, ShieldCheck, VideoOff } from 'lucide-react';

interface Props {
    result: FusedPredictionResponse | null;
}

export default function SensorReliability({ result }: Props) {
    if (!result) return null;

    const reliability = result.tsr_reliability;
    const reasons = result.tsr_discount_reasons;

    // Color mapping based on reliability
    let reliabilityClass = 'low';
    if (reliability < 0.7) reliabilityClass = 'high'; // low reliability is high risk
    else if (reliability < 0.9) reliabilityClass = 'medium';
    else reliabilityClass = 'low';

    const percent = Math.round(reliability * 100);

    return (
        <div className="card system-card system-reliability">
            <div className="card-header">
                <div className="system-label-row">
                    <span className="system-badge sign" style={{ background: 'rgba(129, 140, 248, 0.12)', color: 'var(--accent-primary)' }}>SYSTEM 3</span>
                    <h2 className="card-title">
                        <ShieldCheck size={16} />
                        Sensor Reliability
                    </h2>
                </div>
                <span className="system-status">
                    {percent}% Trust
                </span>
            </div>

            <div className="system-content">
                <div className="system-metrics">
                    <div className="metric-item">
                        <div className={`metric-value level-${reliabilityClass}`}>
                            {percent}%
                        </div>
                        <div className="metric-label">SRD Trust</div>
                    </div>
                    <div className="metric-item">
                        <div className="metric-value" style={{ fontSize: '11px', lineHeight: '1', display: 'flex', alignItems: 'center', justifyContent: 'center', height: '27px' }}>
                            <span className={`status-tag ${result.validation_status.toLowerCase()}`} style={{ fontSize: '9px' }}>
                                {result.validation_status}
                            </span>
                        </div>
                        <div className="metric-label">Logic Stat</div>
                    </div>
                    <div className="metric-item">
                        <div className="metric-value">
                            {result.conflict_measure > 0.3 ? 'Conflict' : 'Stable'}
                        </div>
                        <div className="metric-label">Sync Stat</div>
                    </div>
                </div>

                <div className="reliability-body" style={{ padding: 0, gap: '10px' }}>
                    <div className="reliability-gauge-container">
                        <div
                            className="reliability-gauge-fill"
                            style={{
                                width: `${percent}%`,
                                background: reliability > 0.8 ? 'var(--risk-low)' : reliability > 0.6 ? 'var(--risk-medium)' : 'var(--risk-high)'
                            }}
                        />
                    </div>

                    <div className="reliability-metadata">
                        {reliability === 1.0 ? (
                            <div className="reliability-info-row">
                                <ShieldCheck size={14} className="icon-success" />
                                <span>Optimal sensing conditions</span>
                            </div>
                        ) : (
                            <div className="reliability-info-row">
                                <ShieldAlert size={14} style={{ color: 'var(--risk-medium)' }} />
                                <span style={{ fontSize: '11px' }}>{result.validation_reason || 'Situational discounting active'}</span>
                            </div>
                        )}

                        {reasons.length > 0 && (
                            <ul className="reliability-reasons-list">
                                {reasons.map((r, i) => (
                                    <li key={i}>{r}</li>
                                ))}
                            </ul>
                        )}
                    </div>

                    {reliability < 0.8 && (
                        <div className="reliability-alert">
                            <VideoOff size={14} />
                            <span>GPS evidence prioritized over camera.</span>
                        </div>
                    )}
                </div>
                <p className="system-description">
                    Cross-validates visual detections against situational context and symbolic road rules.
                </p>
            </div>
        </div>
    );
}
