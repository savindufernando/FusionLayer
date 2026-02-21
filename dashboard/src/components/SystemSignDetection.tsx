import type { FusedPredictionResponse, ActiveSign } from '../types';

interface Props {
    result: FusedPredictionResponse | null;
    currentSign: string | null;
}

function formatSignName(name: string): string {
    return name
        .replace(/_/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase())
        .replace(/\(.*?\)/g, match => match.toLowerCase());
}

function signIcon(name: string): string {
    if (name.includes('stop')) return '🛑';
    if (name.includes('curve') || name.includes('double_curve')) return '↪️';
    if (name.includes('slippery')) return '⚠️';
    if (name.includes('pedestrian')) return '🚶';
    if (name.includes('accident')) return '🚨';
    if (name.includes('speed') || name.includes('school')) return '🔢';
    if (name.includes('parking')) return '🅿️';
    if (name.includes('motorway')) return '🛣️';
    if (name.includes('roundabout')) return '🔄';
    if (name.includes('crossing') || name.includes('level')) return '🚧';
    return '🔶';
}

export default function SystemSignDetection({ result, currentSign }: Props) {
    const tsr = result?.tsr_contribution;
    const signs = result?.active_signs || [];

    return (
        <div className="card system-card system-sign">
            <div className="card-header">
                <div className="system-label-row">
                    <span className="system-badge sign">SYSTEM 2</span>
                    <h2 className="card-title">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                            <line x1="12" y1="9" x2="12" y2="13" />
                            <line x1="12" y1="17" x2="12.01" y2="17" />
                        </svg>
                        Dashcam Sign Detection
                    </h2>
                </div>
                <span className="sign-count-badge">{signs.length} active</span>
            </div>
            <div className="system-content">
                {/* Currently detected sign */}
                {tsr?.detected ? (
                    <div className="detected-sign">
                        <span className="detected-sign-icon">{signIcon(tsr.class_name || '')}</span>
                        <div className="detected-sign-info">
                            <div className="detected-sign-name">{formatSignName(tsr.class_name || '')}</div>
                            <div className="detected-sign-meta">
                                Conf: {((tsr.confidence || 0) * 100).toFixed(0)}%
                                {tsr.risk_category && ` · ${tsr.risk_category}`}
                                {tsr.effective_modifier !== undefined && ` · Modifier: ${tsr.effective_modifier.toFixed(2)}`}
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className="detected-sign empty">
                        <span className="detected-sign-icon">📷</span>
                        <div className="detected-sign-info">
                            <div className="detected-sign-name">{currentSign ? formatSignName(currentSign) : 'No sign detected'}</div>
                            <div className="detected-sign-meta">Dashcam scanning road ahead...</div>
                        </div>
                    </div>
                )}

                {/* Active sign buffer */}
                {signs.length > 0 && (
                    <div className="active-signs-list">
                        <div className="signs-header">Active Sign Buffer</div>
                        {signs.map((s: ActiveSign, i: number) => (
                            <div className="sign-item" key={i}>
                                <span className="sign-item-icon">{signIcon(s.class_name)}</span>
                                <div className="sign-item-info">
                                    <span className="sign-item-name">{formatSignName(s.class_name)}</span>
                                    <span className="sign-item-meta">
                                        {(s.confidence * 100).toFixed(0)}% · {s.age_seconds.toFixed(1)}s ago
                                    </span>
                                </div>
                                <span className={`sign-modifier ${s.risk_modifier > 0.5 ? 'high' : s.risk_modifier > 0.2 ? 'medium' : 'low'}`}>
                                    {s.risk_modifier.toFixed(2)}
                                </span>
                            </div>
                        ))}
                    </div>
                )}

                <p className="system-description">
                    Road signs detected by the dashcam with temporal buffering and risk modifiers.
                </p>
            </div>
        </div>
    );
}
