import { useRef, useEffect } from 'react';
import type { FusedPredictionResponse } from '../types';

interface Props {
    isActive: boolean;
    error: string | null;
    onVideoReady: (video: HTMLVideoElement) => void;
    result: FusedPredictionResponse | null;
}

export default function DashcamFeed({ isActive, error, onVideoReady, result }: Props) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const readyFired = useRef(false);

    useEffect(() => {
        if (videoRef.current && !readyFired.current) {
            readyFired.current = true;
            onVideoReady(videoRef.current);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const tsr = result?.tsr_contribution;

    return (
        <div className="card dashcam-card">
            <div className="card-header">
                <h2 className="card-title">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="2" y="3" width="20" height="14" rx="2" />
                        <path d="M8 21h8" />
                        <path d="M12 17v4" />
                    </svg>
                    Dashcam Feed
                </h2>
                <span className={`status-pill ${isActive ? 'online' : error ? 'offline' : ''}`}>
                    <span className="status-dot" />
                    {isActive ? 'LIVE' : error ? 'Error' : 'Waiting...'}
                </span>
            </div>

            <div className="dashcam-content">
                <video
                    ref={videoRef}
                    className="dashcam-video"
                    autoPlay
                    playsInline
                    muted
                />

                {/* No-camera overlay */}
                {!isActive && !error && (
                    <div className="dashcam-overlay">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="1.5">
                            <rect x="2" y="3" width="20" height="14" rx="2" />
                            <circle cx="12" cy="10" r="3" />
                        </svg>
                        <p>Camera will start when you begin tracking</p>
                    </div>
                )}

                {/* Error overlay */}
                {error && (
                    <div className="dashcam-overlay error">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="1.5">
                            <circle cx="12" cy="12" r="10" />
                            <line x1="15" y1="9" x2="9" y2="15" />
                            <line x1="9" y1="9" x2="15" y2="15" />
                        </svg>
                        <p>{error}</p>
                    </div>
                )}

                {/* Sign detection overlay */}
                {isActive && tsr?.detected && (
                    <div className="dashcam-sign-overlay">
                        <div className="detected-sign-badge">
                            <span className="sign-detected-label">DETECTED</span>
                            <span className="sign-detected-name">{tsr.class_name?.replace(/_/g, ' ')}</span>
                            <span className="sign-detected-conf">{((tsr.confidence || 0) * 100).toFixed(0)}%</span>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
