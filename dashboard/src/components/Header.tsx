import { useEffect, useState } from 'react';
import { checkHealth } from '../services/api';

export default function Header() {
    const [status, setStatus] = useState<'connecting' | 'online' | 'offline'>('connecting');
    const [ontologyCount, setOntologyCount] = useState(0);
    const [currentTime, setCurrentTime] = useState(new Date());

    useEffect(() => {
        const timer = setInterval(() => setCurrentTime(new Date()), 1000);
        return () => clearInterval(timer);
    }, []);

    useEffect(() => {
        checkHealth()
            .then(data => {
                setStatus('online');
                setOntologyCount(data.ontology_classes);
            })
            .catch(() => setStatus('offline'));

        const interval = setInterval(() => {
            checkHealth()
                .then(data => {
                    setStatus('online');
                    setOntologyCount(data.ontology_classes);
                })
                .catch(() => setStatus('offline'));
        }, 10000);
        return () => clearInterval(interval);
    }, []);

    return (
        <header className="header">
            <div className="header-left">
                <div className="logo-icon">
                    <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                        <circle cx="16" cy="16" r="14" stroke="#4f46e5" strokeWidth="2.5" fill="none" />
                        <circle cx="16" cy="16" r="8" fill="#4f46e5" opacity="0.15" />
                        <circle cx="16" cy="16" r="4" fill="#4f46e5" />
                        <path d="M16 2 L16 6 M16 26 L16 30 M2 16 L6 16 M26 16 L30 16" stroke="#4f46e5" strokeWidth="1.5" />
                    </svg>
                </div>
                <div>
                    <h1 className="logo-title">DriveGuard</h1>
                    <p className="logo-subtitle">Fusion Risk Intelligence System</p>
                </div>
            </div>
            <div className="header-right">
                <div className="header-time">
                    {currentTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </div>
                <div className={`status-pill ${status}`}>
                    <span className="status-dot" />
                    <span>
                        {status === 'connecting' && 'Connecting...'}
                        {status === 'online' && `API Online · ${ontologyCount} signs`}
                        {status === 'offline' && 'API Offline'}
                    </span>
                </div>
            </div>
        </header>
    );
}
