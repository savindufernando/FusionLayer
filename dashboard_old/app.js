/* ===================================================================
   Fusion Layer Dashboard — Application Logic
   =================================================================== */

const API_BASE = 'http://127.0.0.1:8002';
let map, marker;

// ─── Init ─────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    bindSliders();
    checkHealth();
});

function initMap() {
    map = L.map('map', {
        center: [6.9271, 79.8612],
        zoom: 13,
        zoomControl: false,
        attributionControl: false
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        maxZoom: 19
    }).addTo(map);

    marker = L.marker([6.9271, 79.8612], {
        draggable: true,
        icon: L.divIcon({
            className: 'map-marker-custom',
            html: `<div style="
                width: 18px; height: 18px;
                background: #6366f1;
                border: 3px solid white;
                border-radius: 50%;
                box-shadow: 0 0 12px rgba(99,102,241,0.6);
            "></div>`,
            iconSize: [18, 18],
            iconAnchor: [9, 9]
        })
    }).addTo(map);

    marker.on('dragend', () => {
        const pos = marker.getLatLng();
        document.getElementById('coordsBadge').textContent =
            `${pos.lat.toFixed(4)}, ${pos.lng.toFixed(4)}`;
    });

    // Remove dark filter that we applied via CSS - use CartoDB dark tiles instead
    setTimeout(() => {
        const pane = document.querySelector('.leaflet-tile-pane');
        if (pane) pane.style.filter = 'none';
    }, 500);
}

function bindSliders() {
    const dzScore = document.getElementById('dzScore');
    const dzConf = document.getElementById('dzConf');
    const hotspot = document.getElementById('hotspotBoost');

    dzScore.addEventListener('input', () => {
        document.getElementById('dzScoreVal').textContent = dzScore.value;
    });
    dzConf.addEventListener('input', () => {
        document.getElementById('dzConfVal').textContent = (dzConf.value / 100).toFixed(2);
    });
    hotspot.addEventListener('input', () => {
        document.getElementById('hotspotVal').textContent = (hotspot.value / 100).toFixed(2);
    });
}

async function checkHealth() {
    const el = document.getElementById('apiStatus');
    try {
        const res = await fetch(`${API_BASE}/api/fusion/health`);
        if (res.ok) {
            const data = await res.json();
            el.className = 'status-indicator connected';
            el.querySelector('.status-text').textContent =
                `API Online · ${data.ontology_classes} signs`;
        } else {
            throw new Error('Not OK');
        }
    } catch {
        el.className = 'status-indicator error';
        el.querySelector('.status-text').textContent = 'API Offline';
    }
}

// ─── Fusion ───────────────────────────────────────────────────────

async function runFusion() {
    const btn = document.getElementById('fuseBtn');
    btn.classList.add('loading');
    btn.textContent = 'Fusing...';

    const dzScore = parseFloat(document.getElementById('dzScore').value);
    const dzConf = parseFloat(document.getElementById('dzConf').value) / 100;
    const speed = parseFloat(document.getElementById('speedInput').value);
    const hotspotBoost = parseFloat(document.getElementById('hotspotBoost').value) / 100;
    const [weather, surface] = document.getElementById('weatherSelect').value.split('|');

    let riskLevel = 'LOW';
    if (dzScore >= 65) riskLevel = 'HIGH';
    else if (dzScore >= 35) riskLevel = 'MEDIUM';

    const body = {
        dz_risk_score: dzScore,
        dz_risk_level: riskLevel,
        dz_confidence: dzConf,
        weather_condition: weather,
        road_surface: surface,
        speed_kph: speed,
        hotspot_boost: hotspotBoost,
        hotspot_reports: hotspotBoost > 0 ? 5 : 0
    };

    // Add TSR if selected
    const signVal = document.getElementById('signSelect').value;
    if (signVal) {
        const [classId, className, conf] = signVal.split('|');
        body.tsr_input = {
            class_id: parseInt(classId),
            class_name: className,
            confidence: parseFloat(conf)
        };
    }

    try {
        const res = await fetch(`${API_BASE}/api/fused-predict`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Fusion failed');
        }

        const data = await res.json();
        updateDashboard(data);
    } catch (err) {
        console.error('Fusion error:', err);
        alert('Fusion failed: ' + err.message);
    } finally {
        btn.classList.remove('loading');
        btn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Fuse`;
    }
}

// ─── Update Dashboard ─────────────────────────────────────────────

function updateDashboard(data) {
    updateGauge(data.fused_risk_score, data.fused_risk_level);
    updateDSPanel(data);
    updateContributions(data);
    updateSigns(data.active_signs);
    updateReasons(data.fusion_reasons);
}

function updateGauge(score, level) {
    // Animate gauge arc
    const arc = document.getElementById('gaugeArc');
    const totalLen = 251; // approximate arc length
    const fillLen = (score / 100) * totalLen;
    arc.setAttribute('stroke-dasharray', `${fillLen} ${totalLen}`);

    // Animate needle
    const needle = document.getElementById('gaugeNeedle');
    const angle = -90 + (score / 100) * 180; // -90 to +90 degrees
    needle.setAttribute('transform', `rotate(${angle} 100 100)`);

    // Value
    const val = document.getElementById('gaugeValue');
    animateNumber(val, parseFloat(val.textContent) || 0, score, 600);

    // Color based on level
    const colors = { LOW: '#22c55e', MEDIUM: '#eab308', HIGH: '#ef4444' };
    val.style.color = colors[level] || '#e4e4ef';

    // Badge
    const badge = document.getElementById('riskBadge');
    badge.textContent = level;
    badge.className = `badge badge-${level.toLowerCase()}`;
}

function updateDSPanel(data) {
    const bel = data.belief_dangerous;
    const pl = data.plausibility_dangerous;
    const pig = data.pignistic_probability;

    // Values
    document.getElementById('belValue').textContent = bel.toFixed(3);
    document.getElementById('plValue').textContent = pl.toFixed(3);
    document.getElementById('pigValue').textContent = pig.toFixed(3);
    document.getElementById('conflictValue').textContent = data.conflict_measure.toFixed(3);
    document.getElementById('uncertaintyValue').textContent = data.uncertainty_width.toFixed(3);
    document.getElementById('confidenceValue').textContent = data.fused_confidence.toFixed(3);

    // Belief bar
    document.getElementById('belBar').style.width = `${bel * 100}%`;

    // Uncertainty bar (gap between Bel and Pl)
    const uncBar = document.getElementById('uncBar');
    uncBar.style.left = `${bel * 100}%`;
    uncBar.style.width = `${(pl - bel) * 100}%`;

    // Pignistic marker
    document.getElementById('pigMarker').style.left = `${pig * 100}%`;

    // Color conflict metric
    const conflictEl = document.getElementById('conflictValue');
    if (data.conflict_measure > 0.3) {
        conflictEl.style.color = '#ef4444';
    } else if (data.conflict_measure > 0.1) {
        conflictEl.style.color = '#eab308';
    } else {
        conflictEl.style.color = '#22c55e';
    }
}

function updateContributions(data) {
    // DZ
    const dz = data.dz_contribution;
    document.getElementById('dzContribBadge').textContent = `${dz.risk_score} / ${dz.risk_level}`;
    document.getElementById('dzContribDetails').innerHTML =
        `<span class="contrib-detail-item">Score: ${dz.risk_score}</span>
         <span class="contrib-detail-item">Conf: ${(dz.confidence * 100).toFixed(0)}%</span>
         <span class="contrib-detail-item">Level: ${dz.risk_level}</span>`;

    // TSR
    const tsr = data.tsr_contribution;
    if (tsr.detected) {
        document.getElementById('tsrContribBadge').textContent = tsr.class_name;
        let details = `<span class="contrib-detail-item">Sign: ${tsr.class_name}</span>
                       <span class="contrib-detail-item">Conf: ${(tsr.confidence * 100).toFixed(0)}%</span>`;
        if (tsr.effective_modifier !== undefined) {
            details += `<span class="contrib-detail-item">Modifier: ${tsr.effective_modifier.toFixed(2)}</span>`;
        }
        if (tsr.risk_category) {
            details += `<span class="contrib-detail-item">${tsr.risk_category}</span>`;
        }
        document.getElementById('tsrContribDetails').innerHTML = details;
    } else {
        document.getElementById('tsrContribBadge').textContent = 'None';
        document.getElementById('tsrContribDetails').innerHTML =
            '<span class="contrib-detail-item">No sign detected</span>';
    }

    // Hotspot
    const hot = data.hotspot_contribution;
    if (hot.active) {
        document.getElementById('hotContribBadge').textContent = `+${(hot.risk_boost * 100).toFixed(0)}%`;
        document.getElementById('hotContribDetails').innerHTML =
            `<span class="contrib-detail-item">Boost: ${hot.risk_boost.toFixed(2)}</span>
             <span class="contrib-detail-item">Reports: ${hot.report_count}</span>`;
    } else {
        document.getElementById('hotContribBadge').textContent = 'Inactive';
        document.getElementById('hotContribDetails').innerHTML =
            '<span class="contrib-detail-item">No hotspot data</span>';
    }
}

function updateSigns(signs) {
    const list = document.getElementById('signsList');
    const badge = document.getElementById('signCountBadge');
    badge.textContent = signs.length;

    if (signs.length === 0) {
        list.innerHTML = '<div class="signs-empty">No active signs in buffer</div>';
        return;
    }

    list.innerHTML = signs.map(s => {
        const modColor = s.risk_modifier > 0.5 ? '#ef4444' :
            s.risk_modifier > 0.2 ? '#eab308' : '#22c55e';
        return `
            <div class="sign-item">
                <div class="sign-icon">${s.class_name.substring(0, 2).toUpperCase()}</div>
                <div class="sign-info">
                    <div class="sign-name">${formatSignName(s.class_name)}</div>
                    <div class="sign-meta">Conf: ${(s.confidence * 100).toFixed(0)}% · ${s.age_seconds.toFixed(1)}s ago</div>
                </div>
                <span class="sign-modifier" style="color: ${modColor}">${s.risk_modifier.toFixed(2)}</span>
            </div>`;
    }).join('');
}

function updateReasons(reasons) {
    const list = document.getElementById('reasonsList');
    if (reasons.length === 0) {
        list.innerHTML = '<div class="signs-empty">No risk factors identified</div>';
        return;
    }

    list.innerHTML = reasons.map(r => `
        <div class="reason-item impact-${r.impact}">
            <span class="reason-source">${r.source}</span>
            <span class="reason-text">${r.description}</span>
        </div>`
    ).join('');
}

// ─── Scenarios ────────────────────────────────────────────────────

const SCENARIOS = {
    curve_rain: {
        dzScore: 42, dzConf: 88, sign: '87|curve_to_left|0.94',
        weather: 'Rain|Wet', speed: 55, hotspot: 0
    },
    slippery_rain: {
        dzScore: 50, dzConf: 86, sign: '112|slippery_road|0.90',
        weather: 'Rain|Wet', speed: 50, hotspot: 0
    },
    accident_high: {
        dzScore: 75, dzConf: 92, sign: '83|accident|0.95',
        weather: 'Fine|Dry', speed: 60, hotspot: 0
    },
    safe_parking: {
        dzScore: 15, dzConf: 90, sign: '13|parking|0.95',
        weather: 'Fine|Dry', speed: 30, hotspot: 0
    },
    night_crossing: {
        dzScore: 55, dzConf: 84, sign: '102|level_crossing_without_barriers_ahead|0.87',
        weather: 'Dark|Dry', speed: 45, hotspot: 0
    },
    school_zone: {
        dzScore: 45, dzConf: 85,
        sign: '68|maximum_speed_limit_(all_vehicles_within_school_areas_and_hospitals)|0.88',
        weather: 'Fine|Dry', speed: 35, hotspot: 0
    }
};

function loadScenario(name) {
    const s = SCENARIOS[name];
    if (!s) return;

    document.getElementById('dzScore').value = s.dzScore;
    document.getElementById('dzScoreVal').textContent = s.dzScore;
    document.getElementById('dzConf').value = s.dzConf;
    document.getElementById('dzConfVal').textContent = (s.dzConf / 100).toFixed(2);
    document.getElementById('signSelect').value = s.sign;
    document.getElementById('weatherSelect').value = s.weather;
    document.getElementById('speedInput').value = s.speed;
    document.getElementById('hotspotBoost').value = s.hotspot;
    document.getElementById('hotspotVal').textContent = (s.hotspot / 100).toFixed(2);

    // Auto-fuse after loading scenario
    runFusion();
}

async function resetEngine() {
    try {
        await fetch(`${API_BASE}/api/fusion/reset`, { method: 'POST' });
        // Reset UI
        document.getElementById('gaugeValue').textContent = '—';
        document.getElementById('gaugeValue').style.color = 'var(--text-primary)';
        document.getElementById('gaugeArc').setAttribute('stroke-dasharray', '0 999');
        document.getElementById('gaugeNeedle').setAttribute('transform', 'rotate(-90 100 100)');
        document.getElementById('riskBadge').textContent = '—';
        document.getElementById('riskBadge').className = 'badge badge-subtle';
        document.getElementById('signsList').innerHTML =
            '<div class="signs-empty">Buffer cleared</div>';
        document.getElementById('signCountBadge').textContent = '0';
        document.getElementById('reasonsList').innerHTML =
            '<div class="signs-empty">Engine reset</div>';

        // Reset DS panel
        ['belValue', 'plValue', 'pigValue', 'conflictValue',
            'uncertaintyValue', 'confidenceValue'].forEach(id => {
                document.getElementById(id).textContent = '—';
            });
        document.getElementById('belBar').style.width = '0%';
        document.getElementById('uncBar').style.width = '0%';
        document.getElementById('pigMarker').style.left = '0%';
    } catch (err) {
        console.error('Reset error:', err);
    }
}

// ─── Helpers ──────────────────────────────────────────────────────

function formatSignName(name) {
    return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function animateNumber(el, from, to, duration) {
    const start = performance.now();
    const diff = to - from;

    function update(time) {
        const elapsed = time - start;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
        const current = from + diff * eased;
        el.textContent = current.toFixed(1);
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}
