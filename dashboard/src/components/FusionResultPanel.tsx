import type { FusedPredictionResponse } from '../types';
import { TriangleAlert } from 'lucide-react';

interface Props {
    result: FusedPredictionResponse | null;
}

export default function FusionResultPanel({ result }: Props) {
    if (!result) {
        return (
            <div className="card fusion-card">
                <div className="card-header">
                    <h2 className="card-title">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M8 3H2v15h7c1.7 0 3 1.3 3 3V7c0-2.2-1.8-4-4-4z" />
                            <path d="M16 3h6v15h-7c-1.7 0-3 1.3-3 3V7c0-2.2 1.8-4 4-4z" />
                        </svg>
                        Dempster-Shafer Fusion
                    </h2>
                </div>
                <div className="fusion-content">
                    <p className="system-waiting">Awaiting fusion result from both systems...</p>
                </div>
            </div>
        );
    }

    const bel = result.belief_dangerous;
    const pl = result.plausibility_dangerous;
    const pig = result.pignistic_probability;

    return (
        <div className="card fusion-card">
            <div className="card-header">
                <h2 className="card-title">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M8 3H2v15h7c1.7 0 3 1.3 3 3V7c0-2.2-1.8-4-4-4z" />
                        <path d="M16 3h6v15h-7c-1.7 0-3 1.3-3 3V7c0-2.2 1.8-4 4-4z" />
                    </svg>
                    Dempster-Shafer Fusion
                </h2>
                <span className="method-badge">{result.fusion_method}</span>
            </div>
            <div className="fusion-content">
                {result.adaptive_weights?.degraded && (
                    <div className="degraded-warning" style={{
                        background: 'rgba(245, 158, 11, 0.1)',
                        border: '1px solid rgba(245, 158, 11, 0.3)',
                        borderRadius: '6px',
                        padding: '8px 12px',
                        marginBottom: '1rem',
                        color: '#f59e0b',
                        fontSize: '13px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                    }}>
                        <span><TriangleAlert size={14} /></span>
                        <span>
                            <strong>Partial Fusion:</strong> Some modules are unavailable.
                            DZ: <em>{result.adaptive_weights.dz_circuit}</em> |
                            TSR: <em>{result.adaptive_weights.tsr_circuit}</em>
                        </span>
                    </div>
                )}
                {/* Belief-Plausibility Bar */}
                <div className="bp-section">
                    <div className="bp-labels">
                        <span>Bel(D) = {bel.toFixed(3)}</span>
                        <span>Pl(D) = {pl.toFixed(3)}</span>
                    </div>
                    <div className="bp-bar-track">
                        <div className="bp-bar-bel" style={{ width: `${bel * 100}%` }} />
                        <div className="bp-bar-unc" style={{ left: `${bel * 100}%`, width: `${(pl - bel) * 100}%` }} />
                        <div className="bp-marker" style={{ left: `${pig * 100}%` }} title={`BetP(D) = ${pig.toFixed(3)}`} />
                    </div>
                    <div className="bp-legend">
                        <span className="bp-leg-item"><span className="bp-dot bel" />Belief</span>
                        <span className="bp-leg-item"><span className="bp-dot unc" />Uncertainty</span>
                        <span className="bp-leg-item"><span className="bp-dot pig" />BetP(D)</span>
                    </div>
                </div>

                {/* DS Metrics */}
                <div className="ds-metrics-grid">
                    <div className="ds-metric">
                        <div className="ds-metric-val">{pig.toFixed(3)}</div>
                        <div className="ds-metric-label">BetP(D)</div>
                    </div>
                    <div className="ds-metric">
                        <div className={`ds-metric-val ${result.conflict_measure > 0.3 ? 'conflict-high' : result.conflict_measure > 0.1 ? 'conflict-med' : 'conflict-low'}`}>
                            {result.conflict_measure.toFixed(3)}
                        </div>
                        <div className="ds-metric-label">Conflict K</div>
                    </div>
                    <div className="ds-metric">
                        <div className="ds-metric-val">{result.uncertainty_width.toFixed(3)}</div>
                        <div className="ds-metric-label">Uncertainty</div>
                    </div>
                    <div className="ds-metric">
                        <div className="ds-metric-val">{result.fused_confidence.toFixed(3)}</div>
                        <div className="ds-metric-label">Confidence</div>
                    </div>
                </div>

                {/* Explainability Reasons */}
                {result.fusion_reasons.length > 0 && (
                    <div className="reasons-section">
                        <div className="reasons-label">Risk Factors</div>
                        {result.fusion_reasons.map((r, i) => (
                            <div className={`reason-item ${r.impact}`} key={i}>
                                <span className="reason-source">{r.source.toUpperCase()}</span>
                                <span className="reason-text">{r.description}</span>
                                <span className={`reason-impact ${r.impact}`}>
                                    {r.impact === 'increases_risk' ? '↑' : r.impact === 'decreases_risk' ? '↓' : '—'}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
