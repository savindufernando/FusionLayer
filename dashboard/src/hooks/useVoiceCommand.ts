import { useState, useEffect, useCallback, useRef } from 'react';

export interface VoiceCommandState {
    isListening: boolean;
    transcript: string;
    lastCommand: string | null;
    error: string | null;
    lang: string;
}

export function useVoiceCommand() {
    const [state, setState] = useState<VoiceCommandState>({
        isListening: false,
        transcript: '',
        lastCommand: null,
        error: null,
        lang: 'en-US'
    });

    // Allow external language control
    const setLanguage = useCallback((lang: string) => {
        setState(s => ({ ...s, lang }));
    }, []);

    const recognitionRef = useRef<any>(null);
    const commandsRef = useRef<Record<string, () => void>>({});

    useEffect(() => {
        // @ts-ignore
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!SpeechRecognition) {
            setState(s => ({ ...s, error: "Browser not supported" }));
            return;
        }

        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = false;
        recognition.lang = state.lang; // Use dynamic language

        recognition.onstart = () => {
            setState(s => ({ ...s, isListening: true, error: null }));
        };

        recognition.onresult = (event: any) => {
            const last = event.results.length - 1;
            const transcript = event.results[last][0].transcript.trim().toLowerCase();

            setState(s => ({ ...s, transcript }));
            console.log("Voice Heard:", transcript);

            // Command Matching
            let matched = false;
            Object.entries(commandsRef.current).forEach(([keyword, handler]) => {
                if (transcript.includes(keyword.toLowerCase())) {
                    console.log("Voice Matched command:", keyword);
                    setState(s => ({ ...s, lastCommand: keyword }));
                    handler();
                    matched = true;
                }
            });

            if (!matched && (transcript.includes("drive guard") || transcript.includes("driveguard"))) {
                // Wake word detected but no command?
                // Maybe play a sound?
            }
        };

        recognition.onerror = (event: any) => {
            console.error("Speech error", event.error);
            if (event.error === 'not-allowed') {
                setState(s => ({ ...s, error: "Microphone blocked", isListening: false }));
            }
        };

        recognition.onend = () => {
            setState(s => ({ ...s, isListening: false }));
        };

        recognitionRef.current = recognition;

        return () => {
            recognition.abort();
        };
    }, []);

    const registerCommand = useCallback((keyword: string, handler: () => void) => {
        commandsRef.current[keyword.toLowerCase()] = handler;
    }, []);

    const startListening = useCallback(() => {
        if (recognitionRef.current) {
            try {
                recognitionRef.current.start();
            } catch (e) {
                // already started
            }
        }
    }, []);

    const stopListening = useCallback(() => {
        if (recognitionRef.current) {
            recognitionRef.current.stop();
        }
    }, []);

    return {
        state,
        setLanguage,
        registerCommand,
        startListening,
        stopListening
    };
}
