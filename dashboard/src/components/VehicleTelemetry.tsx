interface TelemetryProps {
    speed: number;
    heading: number;
    lat: number;
    lng: number;
    accuracy: number;
    isTracking: boolean;
    weather: string;
}

function formatHeading(deg: number): string {
    const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
    return dirs[Math.round(deg / 45) % 8];
}

export default function VehicleTelemetry({ speed, heading, lat, lng, accuracy, isTracking, weather }: TelemetryProps) {
    return (
        <div className="card telemetry-card">
            <div className="card-header">
                <h2 className="card-title">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                        <circle cx="12" cy="10" r="3" />
                    </svg>
                    Vehicle Telemetry
                </h2>
                <span className={`status-pill ${isTracking ? 'online' : ''}`}>
                    <span className="status-dot" />
                    {isTracking ? 'LIVE GPS' : 'NO FIX'}
                </span>
            </div>
            <div className="telemetry-grid">
                <div className="telemetry-item">
                    <div className="telemetry-value">{speed}</div>
                    <div className="telemetry-unit">km/h</div>
                    <div className="telemetry-label">Speed</div>
                </div>
                <div className="telemetry-item">
                    <div className="telemetry-value">{heading}°</div>
                    <div className="telemetry-unit">{formatHeading(heading)}</div>
                    <div className="telemetry-label">Heading</div>
                </div>
                <div className="telemetry-item">
                    <div className="telemetry-value">{lat.toFixed(5)}</div>
                    <div className="telemetry-unit">°N</div>
                    <div className="telemetry-label">Latitude</div>
                </div>
                <div className="telemetry-item">
                    <div className="telemetry-value">{lng.toFixed(5)}</div>
                    <div className="telemetry-unit">°E</div>
                    <div className="telemetry-label">Longitude</div>
                </div>
                <div className="telemetry-item">
                    <div className="telemetry-value">±{accuracy}</div>
                    <div className="telemetry-unit">m</div>
                    <div className="telemetry-label">GPS Accuracy</div>
                </div>
                <div className="telemetry-item telemetry-weather">
                    {weather === 'realtime' && '☁️'}
                    {weather === 'sunny' && '☀️'}
                    {weather === 'rain' && '🌧️'}
                    {weather === 'fog' && '🌫️'}
                    {weather === 'night' && '🌙'}
                    {weather === 'storm' && '⛈️'}
                    {weather === 'peak' && '🚦'}
                    <div className="telemetry-unit">&nbsp;</div>
                    <div className="telemetry-label">{weather}</div>
                </div>
            </div>
        </div>
    );
}
