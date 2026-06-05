import { useState, useRef, useCallback, useEffect } from 'react';

/**
 * Hook that accesses the device camera (webcam/phone camera) as a dashcam.
 * Captures frames as base64 JPEG to send to the TSR module.
 */
export function useDashcam() {
    const [isActive, setIsActive] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const canvasRef = useRef<HTMLCanvasElement | null>(null);

    const startCamera = useCallback(async (videoElement: HTMLVideoElement) => {
        try {
            setError(null);
            videoRef.current = videoElement;

            // Prefer rear camera (for phone dashcam use)
            const stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    facingMode: { ideal: 'environment' },
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                }
            });

            streamRef.current = stream;
            videoElement.srcObject = stream;
            await videoElement.play();
            setIsActive(true);

            // Create offscreen canvas for frame capture
            const canvas = document.createElement('canvas');
            canvas.width = 640;
            canvas.height = 480;
            canvasRef.current = canvas;
        } catch (err) {
            const msg = (err as Error).message;
            if (msg.includes('Permission') || msg.includes('NotAllowed')) {
                setError('Camera permission denied. Please allow camera access.');
            } else if (msg.includes('NotFound')) {
                setError('No camera found on this device.');
            } else {
                setError(`Camera error: ${msg}`);
            }
            setIsActive(false);
        }
    }, []);

    const startVideoFile = useCallback(async (videoElement: HTMLVideoElement, file: File) => {
        try {
            setError(null);
            videoRef.current = videoElement;

            const url = URL.createObjectURL(file);
            videoElement.srcObject = null;
            videoElement.src = url;
            videoElement.loop = true;
            await videoElement.play();
            setIsActive(true);

            const canvas = document.createElement('canvas');
            canvas.width = 640;
            canvas.height = 480;
            canvasRef.current = canvas;
        } catch (err) {
            setError(`Video error: ${(err as Error).message}`);
            setIsActive(false);
        }
    }, []);

    const stopCamera = useCallback(() => {
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(track => track.stop());
            streamRef.current = null;
        }
        if (videoRef.current) {
            videoRef.current.pause();
            videoRef.current.srcObject = null;
            videoRef.current.src = "";
            videoRef.current.removeAttribute('src');
        }
        setIsActive(false);
    }, []);

    /**
     * Capture the current camera frame as a base64 JPEG string.
     * Returns null if camera isn't active.
     */
    const captureFrame = useCallback((bbox?: [number, number, number, number]): string | null => {
        if (!videoRef.current || !canvasRef.current || !isActive) return null;

        const video = videoRef.current;
        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d');
        if (!ctx) return null;

        if (bbox) {
            const [x, y, width, height] = bbox;
            // Pad slightly for better context
            const pad = 10;
            const cx = Math.max(0, x - pad);
            const cy = Math.max(0, y - pad);
            const cw = Math.min(width + pad * 2, video.videoWidth - cx);
            const ch = Math.min(height + pad * 2, video.videoHeight - cy);
            
            canvas.width = cw;
            canvas.height = ch;
            ctx.drawImage(video, cx, cy, cw, ch, 0, 0, cw, ch);
        } else {
            canvas.width = 640;
            canvas.height = 480;
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        }

        // Convert to base64 JPEG (remove the data:image/jpeg;base64, prefix)
        const dataUrl = canvas.toDataURL('image/jpeg', 0.6);
        return dataUrl.split(',')[1];
    }, [isActive]);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (streamRef.current) {
                streamRef.current.getTracks().forEach(track => track.stop());
            }
        };
    }, []);

    return { isActive, error, startCamera, startVideoFile, stopCamera, captureFrame };
}
