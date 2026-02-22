import { useEffect, useCallback } from 'react';

interface ShortcutHandlers {
    onStartStop: () => void;
    onReset: () => void;
    onDownloadReport: () => void;
    onToggleHistory: () => void;
    onToggleTheme: () => void;
}

/**
 * Keyboard shortcuts hook.
 * 
 * Shortcuts:
 *   Space  — Start / Stop tracking
 *   R      — Reset trip
 *   D      — Download trip report
 *   H      — Toggle history panel
 *   T      — Toggle dark/light theme
 * 
 * All shortcuts are ignored when the user is focused on an input field.
 */
export function useKeyboardShortcuts({
    onStartStop,
    onReset,
    onDownloadReport,
    onToggleHistory,
    onToggleTheme,
}: ShortcutHandlers) {
    const handleKeyDown = useCallback((e: KeyboardEvent) => {
        // Ignore when typing in an input / textarea / contenteditable
        const tag = (e.target as HTMLElement).tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target as HTMLElement).isContentEditable) {
            return;
        }

        switch (e.key) {
            case ' ':
                e.preventDefault();
                onStartStop();
                break;
            case 'r':
            case 'R':
                if (!e.ctrlKey && !e.metaKey) {
                    e.preventDefault();
                    onReset();
                }
                break;
            case 'd':
            case 'D':
                if (!e.ctrlKey && !e.metaKey) {
                    e.preventDefault();
                    onDownloadReport();
                }
                break;
            case 'h':
            case 'H':
                if (!e.ctrlKey && !e.metaKey) {
                    e.preventDefault();
                    onToggleHistory();
                }
                break;
            case 't':
            case 'T':
                if (!e.ctrlKey && !e.metaKey) {
                    e.preventDefault();
                    onToggleTheme();
                }
                break;
        }
    }, [onStartStop, onReset, onDownloadReport, onToggleHistory, onToggleTheme]);

    useEffect(() => {
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [handleKeyDown]);
}
