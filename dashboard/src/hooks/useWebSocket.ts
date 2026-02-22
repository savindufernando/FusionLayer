import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Hook for managing a WebSocket connection to the Fusion API.
 * Automatically reconnects on failure with exponential backoff.
 */
export function useWebSocket<T>(url: string) {
    const [lastMessage, setLastMessage] = useState<T | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const ws = useRef<WebSocket | null>(null);
    const reconnectAttempts = useRef(0);
    const maxReconnectAttempts = 10;

    const connect = useCallback(() => {
        try {
            // Determine absolute WS URL
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.host;
            const wsUrl = url.startsWith('ws') ? url : `${protocol}//${host}${url}`;

            console.log(`Connecting to WebSocket: ${wsUrl}`);
            const socket = new WebSocket(wsUrl);

            socket.onopen = () => {
                console.log('WebSocket Connected');
                setIsConnected(true);
                setError(null);
                reconnectAttempts.current = 0;
            };

            socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    setLastMessage(data);
                } catch (e) {
                    console.error('WebSocket message parse error:', e);
                }
            };

            socket.onclose = (event) => {
                setIsConnected(false);
                if (!event.wasClean) {
                    console.warn(`WebSocket closed unexpectedly: ${event.code}`);
                    // Exponential backoff reconnect
                    const timeout = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
                    if (reconnectAttempts.current < maxReconnectAttempts) {
                        reconnectAttempts.current++;
                        setTimeout(connect, timeout);
                    } else {
                        setError('WebSocket reconnection failed after multiple attempts');
                    }
                }
            };

            socket.onerror = () => {
                setError('WebSocket connection error');
            };

            ws.current = socket;
        } catch (e) {
            setError(`Failed to create WebSocket: ${(e as Error).message}`);
        }
    }, [url]);

    useEffect(() => {
        connect();
        return () => {
            if (ws.current) {
                ws.current.close(1000, 'Component unmounting');
            }
        };
    }, [connect]);

    return { lastMessage, isConnected, error };
}
