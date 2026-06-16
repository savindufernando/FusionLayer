import { useRef, useEffect, useState } from 'react';
import * as tf from '@tensorflow/tfjs';
import * as cocoSsd from '@tensorflow-models/coco-ssd';
import type { FusedPredictionResponse } from '../types';

const VEHICLE_CLASSES = ['car', 'motorcycle', 'bus', 'truck', 'bicycle'];

interface Props {
    isActive: boolean;
    error: string | null;
    onVideoReady: (video: HTMLVideoElement) => void;
    onVideoUpload?: (file: File, video: HTMLVideoElement) => void;
    result: FusedPredictionResponse | null;
    onSignBbox?: (bbox: [number, number, number, number] | null) => void;
}

export default function DashcamFeed({ isActive, error, onVideoReady, onVideoUpload, result, onSignBbox }: Props) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const readyFired = useRef(false);
    const cocoModelRef = useRef<cocoSsd.ObjectDetection | null>(null);
    
    const [isModelLoaded, setIsModelLoaded] = useState(false);
    const latestResult = useRef(result);

    useEffect(() => {
        latestResult.current = result;
    }, [result]);

    useEffect(() => {
        if (videoRef.current && !readyFired.current) {
            readyFired.current = true;
            onVideoReady(videoRef.current);
        }
        
        const initModel = async () => {
            try {
                await tf.ready();
                
                let coco: cocoSsd.ObjectDetection | null = null;
                
                try {
                    coco = await cocoSsd.load({ base: 'lite_mobilenet_v2' });
                } catch (e) {
                    console.error("Failed to load COCO-SSD", e);
                }
                
                cocoModelRef.current = coco;
                setIsModelLoaded(true);
                console.log("Edge AI visualizer models loaded in browser");
            } catch (err) {
                console.error("Failed to load edge models", err);
                setIsModelLoaded(true); // Always set true so at least the feed works
            }
        };

        initModel();
    }, []);

    useEffect(() => {
        let animationId: number;
        const detectFrame = async () => {
            if (videoRef.current && canvasRef.current && isModelLoaded && isActive && videoRef.current.readyState >= 2) {
                const video = videoRef.current;
                const canvas = canvasRef.current;
                
                canvas.width = video.clientWidth;
                canvas.height = video.clientHeight;
                
                const ctx = canvas.getContext('2d');
                if (ctx && video.videoWidth > 0 && video.videoHeight > 0) {
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    
                    try {
                        const cocoPromise = cocoModelRef.current ? cocoModelRef.current.detect(video) : Promise.resolve([]);
                        const [cocoPredictions] = await Promise.all([cocoPromise]);
                        
                        let signDetectedBbox: [number, number, number, number] | null = null;

                        // Process COCO-SSD Predictions (Vehicles)
                        cocoPredictions.forEach((prediction: cocoSsd.DetectedObject) => {
                            if (VEHICLE_CLASSES.includes(prediction.class) && prediction.score > 0.45) {
                                const videoRatio = video.videoWidth / video.videoHeight;
                                const containerRatio = canvas.width / canvas.height;
                                
                                let renderWidth, renderHeight, offsetX, offsetY;
                                if (containerRatio > videoRatio) {
                                    renderWidth = canvas.width;
                                    renderHeight = canvas.width / videoRatio;
                                    offsetX = 0;
                                    offsetY = (canvas.height - renderHeight) / 2;
                                } else {
                                    renderHeight = canvas.height;
                                    renderWidth = canvas.height * videoRatio;
                                    offsetX = (canvas.width - renderWidth) / 2;
                                    offsetY = 0;
                                }
                                
                                const scale = renderWidth / video.videoWidth;
                                
                                const [x, y, width, height] = prediction.bbox;
                                const scaledX = (x * scale) + offsetX;
                                const scaledY = (y * scale) + offsetY;
                                const scaledWidth = width * scale;
                                const scaledHeight = height * scale;

                                const strokeColor = '#ef4444'; // Red for vehicles
                                const fillColor = 'rgba(239, 68, 68, 0.9)';

                                // Draw Edge AI Box
                                ctx.strokeStyle = strokeColor;
                                ctx.lineWidth = 2;
                                ctx.strokeRect(scaledX, scaledY, scaledWidth, scaledHeight);
                                
                                // Draw Background Label
                                ctx.fillStyle = fillColor;
                                const text = `${prediction.class.toUpperCase()} ${(prediction.score * 100).toFixed(0)}%`;
                                ctx.font = '10px "JetBrains Mono", monospace';
                                const textWidth = ctx.measureText(text).width;
                                ctx.fillRect(scaledX, scaledY - 16, textWidth + 8, 16);
                                
                                // Draw Text
                                ctx.fillStyle = '#FFFFFF';
                                ctx.fillText(text, scaledX + 4, scaledY - 4);
                            }
                        });
                        
                        if (onSignBbox) {
                            onSignBbox(signDetectedBbox);
                        }
                        
                        const currentResult = latestResult.current;
                        if (currentResult?.tsr_contribution?.detected && currentResult.tsr_contribution.bbox) {
                            const [bx1, by1, bx2, by2] = currentResult.tsr_contribution.bbox;
                            
                            const videoRatio = video.videoWidth / video.videoHeight;
                            const containerRatio = canvas.width / canvas.height;
                            
                            let renderWidth, renderHeight, offsetX, offsetY;
                            if (containerRatio > videoRatio) {
                                renderWidth = canvas.width;
                                renderHeight = canvas.width / videoRatio;
                                offsetX = 0;
                                offsetY = (canvas.height - renderHeight) / 2;
                            } else {
                                renderHeight = canvas.height;
                                renderWidth = canvas.height * videoRatio;
                                offsetX = (canvas.width - renderWidth) / 2;
                                offsetY = 0;
                            }
                            
                            // The API receives a 640x480 downscaled frame from useDashcam.ts
                            // Therefore, the backend's bbox is in 640x480 coordinate space!
                            const tsrScaleX = renderWidth / 640;
                            const tsrScaleY = renderHeight / 480;
                            
                            const scaledX = (bx1 * tsrScaleX) + offsetX;
                            const scaledY = (by1 * tsrScaleY) + offsetY;
                            const scaledWidth = ((bx2 - bx1) * tsrScaleX);
                            const scaledHeight = ((by2 - by1) * tsrScaleY);

                            ctx.strokeStyle = '#3b82f6';
                            ctx.lineWidth = 2;
                            ctx.strokeRect(scaledX, scaledY, scaledWidth, scaledHeight);
                            
                            ctx.fillStyle = 'rgba(59, 130, 246, 0.9)';
                            const signName = currentResult.tsr_contribution.class_name?.replace(/_/g, ' ').toUpperCase() || 'SIGN';
                            const conf = currentResult.tsr_contribution.confidence || 0;
                            const tsrText = `${signName} ${(conf * 100).toFixed(0)}%`;
                            ctx.font = '10px "JetBrains Mono", monospace';
                            const tsrTextWidth = ctx.measureText(tsrText).width;
                            ctx.fillRect(scaledX, scaledY - 16, tsrTextWidth + 8, 16);
                            
                            ctx.fillStyle = '#FFFFFF';
                            ctx.fillText(tsrText, scaledX + 4, scaledY - 4);
                        }
                    } catch (e) {
                        console.error("Error during detection loop:", e);
                    }
                }
            }
            animationId = requestAnimationFrame(detectFrame);
        };

        if (isActive) {
            detectFrame();
        }

        return () => {
            if (animationId) {
                cancelAnimationFrame(animationId);
            }
        };
    }, [isActive, isModelLoaded]);

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
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <label className="btn btn-outline" style={{ fontSize: '10px', padding: '4px 8px', cursor: 'pointer', margin: 0 }}>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '4px' }}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></svg>
                        Upload Video
                        <input type="file" accept="video/mp4,video/webm" style={{ display: 'none' }} onChange={(e) => {
                            if (e.target.files && e.target.files[0] && onVideoUpload && videoRef.current) {
                                onVideoUpload(e.target.files[0], videoRef.current);
                            }
                        }} />
                    </label>
                    <span className={`status-pill ${isActive ? 'online' : error ? 'offline' : ''}`}>
                        <span className="status-dot" />
                        {isActive ? 'LIVE' : error ? 'Error' : 'Waiting...'}
                    </span>
                </div>
            </div>

            <div className="dashcam-content">
                <video
                    ref={videoRef}
                    className="dashcam-video"
                    autoPlay
                    playsInline
                    muted
                />
                <canvas 
                    ref={canvasRef} 
                    style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 5 }}
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
