import { useState, useCallback, useEffect, useRef } from 'react';
import { Mic, MicOff } from 'lucide-react';
import Header from './components/Header';
import MapPanel from './components/MapPanel';
import DashcamFeed from './components/DashcamFeed';
import RiskGauge from './components/RiskGauge';
import VehicleTelemetry from './components/VehicleTelemetry';
import SystemGeolocation from './components/SystemGeolocation';
import SystemSignDetection from './components/SystemSignDetection';
import SensorReliability from './components/SensorReliability';
import FusionResultPanel from './components/FusionResultPanel';
import Controls from './components/Controls';
import HotspotPanel from './components/HotspotPanel';
import HistoryPanel from './components/HistoryPanel';
import { useGPS } from './hooks/useGPS';
import { useDashcam } from './hooks/useDashcam';
import { useRealTimeFusion } from './hooks/useRealTimeFusion';
import { useVoiceAlert } from './hooks/useVoiceAlert';
import { generateTripReport } from './services/report';
import { resetEngine, saveTrip } from './services/api';
import { useVoiceCommand } from './hooks/useVoiceCommand';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import type { WeatherScenario, TripCreate } from './types';

function App() {
  const [weather, setWeather] = useState<WeatherScenario>('sunny');
  const [showHistory, setShowHistory] = useState(false);
  const gps = useGPS();
  const dashcam = useDashcam();
  const fusion = useRealTimeFusion(gps.vehicle, dashcam.captureFrame, weather);

  const handleStart = useCallback(() => {
    gps.startTracking();
    // Camera starts when video element is ready (via onVideoReady)
    fusion.start();
  }, [gps, fusion]);

  const handleStop = useCallback(() => {
    dashcam.stopCamera();

    // Auto-save trip if meaningful
    const stats = fusion.state.tripStats;
    if (stats.startTime && fusion.state.tickCount > 5) {
      const trip: TripCreate = {
        start_time: new Date(stats.startTime).toISOString(),
        end_time: new Date().toISOString(),
        duration_seconds: Math.floor((Date.now() - stats.startTime) / 1000),
        distance_km: stats.distanceKm,
        max_risk: stats.maxRisk,
        avg_risk: stats.avgRisk,
        safety_score: Math.max(0, 100 - stats.avgRisk * 1.5),
        risk_events_count: stats.highRiskEvents.length
      };
      saveTrip(trip).then(() => console.log("Trip saved successfully"))
        .catch(err => console.error("Failed to save trip:", err));
    }

    fusion.stop();
    gps.stopTracking();
  }, [dashcam, fusion, gps]);

  const handleReset = useCallback(async () => {
    handleStop();
    fusion.clearTrail();
    try { await resetEngine(); } catch { /* ignore */ }
  }, [handleStop, fusion]);

  const handleDownloadReport = useCallback(() => {
    generateTripReport(fusion.state.tripStats, fusion.state.fullHistory);
  }, [fusion.state]);

  const handleExportJSON = useCallback(() => {
    const exportData = {
      exportedAt: new Date().toISOString(),
      tripStats: fusion.state.tripStats,
      history: fusion.state.fullHistory,
      tickCount: fusion.state.tickCount,
      lastFusionResult: fusion.state.fusionResult,
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `driveguard-export-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [fusion.state]);

  const handleVideoReady = useCallback((video: HTMLVideoElement) => {
    dashcam.startCamera(video);
  }, [dashcam]);

  // Theme toggle helper (mirrors Header state via DOM)
  const toggleTheme = useCallback(() => {
    const el = document.documentElement;
    const current = el.dataset.theme;
    const next = current === 'dark' ? 'light' : 'dark';
    el.dataset.theme = next;
    localStorage.setItem('dg-theme', next);
  }, []);

  // Keyboard Shortcuts
  useKeyboardShortcuts({
    onStartStop: useCallback(() => {
      if (fusion.state.isRunning) handleStop(); else handleStart();
    }, [fusion.state.isRunning, handleStart, handleStop]),
    onReset: handleReset,
    onDownloadReport: handleDownloadReport,
    onToggleHistory: useCallback(() => setShowHistory(prev => !prev), []),
    onToggleTheme: toggleTheme,
  });

  // Voice Alerts Integration
  const voice = useVoiceAlert();

  useEffect(() => {
    if (fusion.state.fusionResult) {
      const { fused_risk_score, fused_risk_level, hotspot_contribution } = fusion.state.fusionResult;

      // 1. High Risk Alert
      if (fused_risk_level === 'HIGH' || (fused_risk_level === 'MEDIUM' && fused_risk_score > 60)) {
        voice.alertDangerZone(fused_risk_score, fused_risk_level);
      }

      // 2. Black Spot Alert
      if (hotspot_contribution && hotspot_contribution.active) {
        voice.alertHotspot();
      }
    }
  }, [fusion.state.fusionResult, voice]);

  // Voice Command Integration
  const voiceCommand = useVoiceCommand();
  const fusionStateRef = useRef(fusion.state);

  useEffect(() => {
    fusionStateRef.current = fusion.state;
  }, [fusion.state]);

  useEffect(() => {
    voiceCommand.registerCommand('start tracking', handleStart);
    voiceCommand.registerCommand('begin tracking', handleStart);
    voiceCommand.registerCommand('stop tracking', handleStop);
    voiceCommand.registerCommand('end tracking', handleStop);
    voiceCommand.registerCommand('show history', () => setShowHistory(true));
    voiceCommand.registerCommand('close history', () => setShowHistory(false));
    voiceCommand.registerCommand('status', () => {
      const res = fusionStateRef.current.fusionResult;
      if (res) {
        if (voiceCommand.state.lang === 'si-LK') {
          const riskSi = res.fused_risk_level === 'HIGH' ? 'Ithamaavadhaanam' : 'Samanya';
          voice.speak(`Avadhanam mattama ${riskSi}`);
        } else {
          voice.speak(`Current risk is ${res.fused_risk_level}, score ${res.fused_risk_score.toFixed(0)}`);
        }
      } else {
        voice.speak("System initializing");
      }
    });

    // Sinhala Commands
    voiceCommand.registerCommand('vartha karanna', handleStart);
    voiceCommand.registerCommand('navathvanna', handleStop);
    voiceCommand.registerCommand('ithihasaya', () => setShowHistory(true));
    voiceCommand.registerCommand('vasanna', () => setShowHistory(false));
    voiceCommand.registerCommand('thathvaya', () => {
      const res = fusionStateRef.current.fusionResult;
      if (res) {
        if (voiceCommand.state.lang === 'si-LK') {
          const riskSi = res.fused_risk_level === 'HIGH' ? 'Ithamaavadhaanam' : 'Samanya';
          voice.speak(`Avadhanam mattama ${riskSi}`);
        } else {
          voice.speak(`Current risk is ${res.fused_risk_level}, score ${res.fused_risk_score.toFixed(0)}`);
        }
      }
    });

    voiceCommand.startListening();
  }, [handleStart, handleStop, voiceCommand, voice]);

  return (
    <div className="app">
      <Header />
      {/* Voice Status Indicator */}
      <div style={{
        position: 'fixed', top: '1rem', left: '50%', transform: 'translateX(-50%)', zIndex: 3000,
        background: voiceCommand.state.isListening ? 'rgba(34, 197, 94, 0.2)' : 'var(--bg-tertiary)',
        padding: '4px 12px', borderRadius: '16px', backdropFilter: 'blur(4px)',
        border: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: '8px',
        transition: 'all 0.3s'
      }}>
        <span style={{ fontSize: '12px', color: voiceCommand.state.isListening ? '#4ade80' : 'var(--text-tertiary)' }}>
          {voiceCommand.state.isListening ? <Mic size={12} /> : <MicOff size={12} />}
          {voiceCommand.state.lang === 'si-LK' ? ' සිංහල' : ' EN'}
        </span>
        {voiceCommand.state.transcript && (
          <span style={{ fontSize: '12px', color: 'var(--text-primary)', borderLeft: '1px solid var(--border-color)', paddingLeft: '8px' }}>
            "{voiceCommand.state.transcript}"
          </span>
        )}
        {/* Lang Toggle */}
        <button
          onClick={() => voiceCommand.setLanguage(voiceCommand.state.lang === 'en-US' ? 'si-LK' : 'en-US')}
          style={{ background: 'none', border: '1px solid var(--border-color)', color: 'var(--text-tertiary)', borderRadius: '4px', fontSize: '10px', padding: '2px 4px', cursor: 'pointer', marginLeft: '4px' }}
        >
          {voiceCommand.state.lang === 'en-US' ? 'SI' : 'EN'}
        </button>
      </div>

      <main className="dashboard">
        {/* Left Column — Map + Dashcam */}
        <div className="col-left">
          <MapPanel
            lat={gps.vehicle.lat}
            lng={gps.vehicle.lng}
            heading={gps.vehicle.heading}
            trail={fusion.state.trail}
            isMoving={gps.vehicle.isTracking}
          />
          <DashcamFeed
            isActive={dashcam.isActive}
            error={dashcam.error}
            onVideoReady={handleVideoReady}
            result={fusion.state.fusionResult}
          />
          <HotspotPanel
            currentLat={gps.vehicle.lat}
            currentLng={gps.vehicle.lng}
            onHotspotClick={(_lat, _lng) => {
              const mapEl = document.querySelector('.map-container');
              mapEl?.scrollIntoView({ behavior: 'smooth' });
            }}
          />
        </div>

        {/* Right Column — Risk + Systems + Controls */}
        <div className="col-right">
          <div className="top-row">
            <RiskGauge
              score={fusion.state.fusionResult?.fused_risk_score ?? null}
              level={fusion.state.fusionResult?.fused_risk_level ?? null}
              confidence={fusion.state.fusionResult?.fused_confidence ?? null}
              degraded={fusion.state.fusionResult?.adaptive_weights?.degraded}
            />
            <VehicleTelemetry
              speed={gps.vehicle.speed}
              heading={gps.vehicle.heading}
              lat={gps.vehicle.lat}
              lng={gps.vehicle.lng}
              accuracy={gps.vehicle.accuracy}
              isTracking={gps.vehicle.isTracking}
              weather={weather}
            />
          </div>

          <div className="systems-row">
            <SystemGeolocation result={fusion.state.fusionResult} />
            <SystemSignDetection
              result={fusion.state.fusionResult}
              currentSign={null}
            />
            <SensorReliability result={fusion.state.fusionResult} />
          </div>

          <FusionResultPanel result={fusion.state.fusionResult} />

          <Controls
            isTracking={gps.vehicle.isTracking}
            isFusing={fusion.state.isRunning}
            weather={weather}
            gpsPermission={gps.permissionState}
            cameraActive={dashcam.isActive}
            gpsError={gps.error}
            cameraError={dashcam.error}
            tickCount={fusion.state.tickCount}
            onStartTracking={handleStart}
            onStopTracking={handleStop}
            onWeatherChange={setWeather}
            onReset={handleReset}
            onDownloadReport={handleDownloadReport}
            onExportJSON={handleExportJSON}
            hasTripData={fusion.state.tripStats.startTime !== null || fusion.state.tickCount > 10}
            onShowHistory={() => setShowHistory(true)}
          />

          {fusion.state.error && (
            <div className="error-banner">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              {fusion.state.error}
            </div>
          )}
        </div>
        {showHistory && (
          <HistoryPanel onClose={() => setShowHistory(false)} />
        )}
      </main>
    </div>
  );
}

export default App;

