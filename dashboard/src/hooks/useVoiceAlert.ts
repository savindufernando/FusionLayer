import { useRef, useCallback, useEffect } from 'react';

/**
 * Voice alert hook using Web Speech API.
 * Announces danger warnings with separate cooldowns for different alert types.
 */
export function useVoiceAlert() {
    // Separate cooldowns for different alert types
    const lastDangerAlertRef = useRef(0);
    const lastHotspotAlertRef = useRef(0);
    const synthRef = useRef<SpeechSynthesis | null>(null);

    // Initialize speech synthesis
    useEffect(() => {
        if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
            synthRef.current = window.speechSynthesis;
        }
    }, []);

    const speak = useCallback((message: string, priority: 'normal' | 'high' = 'normal') => {
        if (!synthRef.current) return;

        // Cancel any ongoing speech for high priority
        if (priority === 'high') {
            synthRef.current.cancel();
        }

        // Create utterance
        const utterance = new SpeechSynthesisUtterance(message);
        utterance.rate = 1.1;  // Slightly faster
        utterance.pitch = 1.0;
        utterance.volume = 1.0;

        // Try to use a good voice (English Female preferred)
        const voices = synthRef.current.getVoices();
        const preferredVoice = voices.find(v =>
            v.lang.startsWith('en') && (v.name.includes('Google') || v.name.includes('Female') || v.name.includes('Natural'))
        ) || voices.find(v => v.lang.startsWith('en')) || voices[0];

        if (preferredVoice) {
            utterance.voice = preferredVoice;
        }

        synthRef.current.speak(utterance);
    }, []);

    // Danger zone alert with 15s cooldown
    const alertDangerZone = useCallback((riskScore: number, riskLevel: string) => {
        const now = Date.now();
        if (now - lastDangerAlertRef.current < 15000) return;

        if (riskLevel === 'HIGH') {
            speak(`Warning! High risk zone ahead. Risk level ${Math.round(riskScore)} percent. Drive carefully.`, 'high');
            lastDangerAlertRef.current = now;
        } else if (riskLevel === 'MEDIUM' && riskScore > 60) {
            speak(`Caution. Elevated risk ahead. Stay alert.`, 'high');
            lastDangerAlertRef.current = now;
        }
    }, [speak]);

    // Hotspot alert with 20s cooldown
    const alertHotspot = useCallback(() => {
        const now = Date.now();
        if (now - lastHotspotAlertRef.current < 20000) return;

        speak(`Caution! Black spot ahead. High accident frequency reported.`, 'high');
        lastHotspotAlertRef.current = now;
    }, [speak]);

    return {
        speak,
        alertDangerZone,
        alertHotspot
    };
}
