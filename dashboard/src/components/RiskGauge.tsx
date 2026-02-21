import { useEffect, useRef, useMemo } from 'react';

interface RiskGaugeProps {
    score: number | null;
    level: 'LOW' | 'MEDIUM' | 'HIGH' | null;
    confidence: number | null;
}

export default function RiskGauge({ score, level, confidence }: RiskGaugeProps) {
    const displayScore = score ?? 0;
    const displayLevel = level ?? '—';
    const prevScoreRef = useRef(0);

    useEffect(() => {
        if (score !== null) prevScoreRef.current = score;
    }, [score]);

    const gaugeColor = useMemo(() => {
        if (!level) return '#cbd5e1';
        if (level === 'LOW') return '#16a34a';
        if (level === 'MEDIUM') return '#ca8a04';
        return '#dc2626';
    }, [level]);

    // SVG arc parameters
    const radius = 80;
    const cx = 100;
    const cy = 100;
    const startAngle = -210;
    const endAngle = 30;
    const totalArc = endAngle - startAngle; // 240 degrees
    const scoreAngle = startAngle + (displayScore / 100) * totalArc;

    // Arc path calculations
    const polarToCartesian = (angle: number) => {
        const rad = (angle * Math.PI) / 180;
        return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
    };

    const startPt = polarToCartesian(startAngle);
    const endPt = polarToCartesian(endAngle);
    const scorePt = polarToCartesian(scoreAngle);

    const bgArc = `M ${startPt.x} ${startPt.y} A ${radius} ${radius} 0 1 1 ${endPt.x} ${endPt.y}`;
    const needleAngle = scoreAngle;

    // Score arc
    const arcSweep = displayScore / 100 * totalArc;
    const largeArc = arcSweep > 180 ? 1 : 0;
    const scoreArc = `M ${startPt.x} ${startPt.y} A ${radius} ${radius} 0 ${largeArc} 1 ${scorePt.x} ${scorePt.y}`;

    // Needle endpoint
    const needleLen = 60;
    const needleRad = (needleAngle * Math.PI) / 180;
    const needleX = cx + needleLen * Math.cos(needleRad);
    const needleY = cy + needleLen * Math.sin(needleRad);

    return (
        <div className="card gauge-card">
            <div className="card-header">
                <h2 className="card-title">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z" />
                        <path d="M12 6v6l4 2" />
                    </svg>
                    Fused Risk Assessment
                </h2>
                <span className={`risk-badge ${level ? level.toLowerCase() : ''}`}>
                    {displayLevel}
                </span>
            </div>
            <div className="gauge-wrapper">
                <svg viewBox="0 0 200 140" className="gauge-svg">
                    {/* Background arc */}
                    <path d={bgArc} fill="none" stroke="#e2e8f0" strokeWidth="14" strokeLinecap="round" />
                    {/* Score arc */}
                    {score !== null && (
                        <path
                            d={scoreArc}
                            fill="none"
                            stroke={gaugeColor}
                            strokeWidth="14"
                            strokeLinecap="round"
                            style={{ transition: 'all 0.5s ease' }}
                        />
                    )}
                    {/* Needle */}
                    <line
                        x1={cx}
                        y1={cy}
                        x2={needleX}
                        y2={needleY}
                        stroke="#1e293b"
                        strokeWidth="2.5"
                        strokeLinecap="round"
                        style={{ transition: 'all 0.5s ease' }}
                    />
                    <circle cx={cx} cy={cy} r="5" fill="#1e293b" />
                    {/* Scale labels */}
                    <text x="25" y="120" fontSize="10" fill="#94a3b8" textAnchor="middle">0</text>
                    <text x="100" y="20" fontSize="10" fill="#94a3b8" textAnchor="middle">50</text>
                    <text x="175" y="120" fontSize="10" fill="#94a3b8" textAnchor="middle">100</text>
                </svg>
                <div className="gauge-value" style={{ color: gaugeColor }}>
                    {score !== null ? score.toFixed(1) : '—'}
                </div>
                <div className="gauge-label">Fused Risk Score</div>
                {confidence !== null && (
                    <div className="gauge-confidence">Confidence: {(confidence * 100).toFixed(0)}%</div>
                )}
            </div>
        </div>
    );
}
