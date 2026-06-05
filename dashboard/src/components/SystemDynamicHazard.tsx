import { Target, Footprints, Dog, Car, Bike, Truck, AlertOctagon } from 'lucide-react';
import type { FusedPredictionResponse } from '../types';

interface Props {
    result: FusedPredictionResponse | null;
}

function hazardIcon(name: string): React.ReactNode {
    if (name.includes('person') || name.includes('pedestrian')) return <Footprints size={18} />;
    if (name.includes('dog') || name.includes('animal')) return <Dog size={18} />;
    if (name.includes('car') || name.includes('vehicle')) return <Car size={18} />;
    if (name.includes('bicycle') || name.includes('motorcycle')) return <Bike size={18} />;
    if (name.includes('bus') || name.includes('truck')) return <Truck size={18} />;
    return <AlertOctagon size={18} />;
}

export default function SystemDynamicHazard({ result }: Props) {
    const yolo = result?.yolo_contribution;

    return (
        <div className="card system-card system-yolo">
            <div className="card-header">
                <div className="system-label-row">
                    <span className="system-badge yolo">SYSTEM 4</span>
                    <h2 className="card-title">
                        <Target size={18} />
                        Edge AI Dynamic Hazards
                    </h2>
                </div>
            </div>
            <div className="system-content">
                {yolo?.detected ? (
                    <div className="detected-sign" style={{ borderColor: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.05)' }}>
                        <span className="detected-sign-icon" style={{ color: '#ef4444' }}>
                            {hazardIcon(yolo.hazard_class || '')}
                        </span>
                        <div className="detected-sign-info">
                            <div className="detected-sign-name" style={{ color: '#ef4444', fontWeight: 'bold' }}>
                                {(yolo.hazard_class || '').toUpperCase()} DETECTED
                            </div>
                            <div className="detected-sign-meta" style={{ color: '#ef4444' }}>
                                Confidence: {((yolo.confidence || 0) * 100).toFixed(0)}%
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className="detected-sign empty">
                        <span className="detected-sign-icon"><Target size={18} /></span>
                        <div className="detected-sign-info">
                            <div className="detected-sign-name">No dynamic hazards</div>
                            <div className="detected-sign-meta">Edge AI scanning...</div>
                        </div>
                    </div>
                )}
                
                <p className="system-description">
                    YOLOv10 object detection identifying erratic entities in real-time.
                </p>
            </div>
        </div>
    );
}
