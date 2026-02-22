import { useEffect, useState } from 'react';
import { checkHealth } from '../services/api';
import { useWebSocket } from '../hooks/useWebSocket';
import { Moon, Sun, Zap } from 'lucide-react';

export default function Header() {
    const { isConnected: isWS } = useWebSocket('/api/fusion/ws');
    const [status, setStatus] = useState<'connecting' | 'online' | 'offline'>('connecting');
    const [ontologyCount, setOntologyCount] = useState(0);
    const [currentTime, setCurrentTime] = useState(new Date());
    const [theme, setTheme] = useState<'light' | 'dark'>(() => {
        const saved = localStorage.getItem('dg-theme');
        if (saved === 'dark' || saved === 'light') return saved;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    });

    // Apply theme on mount and change
    useEffect(() => {
        document.documentElement.dataset.theme = theme;
        localStorage.setItem('dg-theme', theme);
    }, [theme]);

    const toggleTheme = () => setTheme(prev => prev === 'light' ? 'dark' : 'light');

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
                        <circle cx="16" cy="16" r="14" stroke="var(--accent-primary)" strokeWidth="2.5" fill="none" />
                        <circle cx="16" cy="16" r="8" fill="var(--accent-primary)" opacity="0.15" />
                        <circle cx="16" cy="16" r="4" fill="var(--accent-primary)" />
                        <path d="M16 2 L16 6 M16 26 L16 30 M2 16 L6 16 M26 16 L30 16" stroke="var(--accent-primary)" strokeWidth="1.5" />
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
                <button
                    className="theme-toggle"
                    onClick={toggleTheme}
                    title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode (T)`}
                    aria-label="Toggle theme"
                >
                    {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
                </button>
                <div className={`status-pill ${status}`}>
                    <span className="status-dot" />
                    <span>
                        {status === 'connecting' && 'Connecting...'}
                        {status === 'online' && `API Online · ${ontologyCount} signs`}
                        {status === 'offline' && 'API Offline'}
                    </span>
                    {isWS && (
                        <span className="ws-badge" style={{
                            marginLeft: '8px',
                            background: 'rgba(34, 197, 94, 0.2)',
                            color: '#4ade80',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            fontSize: '10px',
                            fontWeight: 'bold',
                            border: '1px solid rgba(34, 197, 94, 0.3)'
                        }}>
                            <Zap size={10} style={{ display: 'inline' }} /> REAL-TIME
                        </span>
                    )}
                </div>
            </div>
        </header>
    );
}

