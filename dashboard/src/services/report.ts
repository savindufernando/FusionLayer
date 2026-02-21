import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import type { TripStats, TrailPoint } from '../hooks/useRealTimeFusion';

export function generateTripReport(stats: TripStats, history: TrailPoint[]) {
    const doc = new jsPDF();

    // Branding
    doc.setFillColor(79, 70, 229); // Indigo-600
    doc.rect(0, 0, 210, 20, 'F');
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(16);
    doc.text("DriveGuard Fusion - Trip Report", 14, 13);

    // Metadata
    doc.setTextColor(0, 0, 0);
    doc.setFontSize(10);
    const now = new Date();
    doc.text(`Generated: ${now.toLocaleString()}`, 14, 30);

    if (stats.startTime) {
        const start = new Date(stats.startTime);
        // If endTime isn't set (e.g. report generated mid-trip), use now
        const end = stats.endTime ? new Date(stats.endTime) : now;
        doc.text(`Trip Start: ${start.toLocaleString()}`, 14, 35);
        doc.text(`Trip End: ${end.toLocaleString()}`, 14, 40);

        // Calc duration
        const durationSec = (end.getTime() - start.getTime()) / 1000;
        const h = Math.floor(durationSec / 3600);
        const m = Math.floor((durationSec % 3600) / 60);
        const s = Math.floor(durationSec % 60);
        var durationStr = `${h}h ${m}m ${s}s`;
    } else {
        var durationStr = "N/A";
    }

    // Summary Metrics Table
    autoTable(doc, {
        startY: 50,
        head: [['Metric', 'Value']],
        body: [
            ['Duration', durationStr || "0s"],
            ['Distance Traveled', `${stats.distanceKm.toFixed(2)} km`],
            ['Max Risk Score', `${stats.maxRisk.toFixed(1)}%`],
            ['Average Risk Score', `${stats.avgRisk.toFixed(1)}%`],
            ['High Risk Events', `${stats.highRiskEvents.length}`],
            ['Safety Score', `${Math.max(0, 100 - stats.avgRisk * 1.5).toFixed(1)} / 100`],
        ],
        theme: 'striped',
        headStyles: { fillColor: [79, 70, 229] },
    });

    // Route Visualization
    let finalY = (doc as any).lastAutoTable.finalY + 15;

    if (history.length > 1) {
        if (finalY > 200) { doc.addPage(); finalY = 20; }

        doc.setFontSize(14);
        doc.setTextColor(79, 70, 229);
        doc.text("Route Visualization (Path)", 14, finalY);

        const startX = 14;
        const startY = finalY + 5;
        const width = 180;
        const height = 80;

        // Draw box
        doc.setDrawColor(200, 200, 200);
        doc.rect(startX, startY, width, height);

        // Normalize coordinates
        const lats = history.map(p => p.lat);
        const lngs = history.map(p => p.lng);
        const minLat = Math.min(...lats);
        const maxLat = Math.max(...lats);
        const minLng = Math.min(...lngs);
        const maxLng = Math.max(...lngs);

        if (maxLat !== minLat && maxLng !== minLng) {
            const latRange = maxLat - minLat;
            const lngRange = maxLng - minLng;

            doc.setDrawColor(220, 38, 38);
            doc.setLineWidth(0.8);

            for (let i = 0; i < history.length - 1; i++) {
                const p1 = history[i];
                const p2 = history[i + 1];

                // Map to box: verify x/y (lat maps to Y inverted, lng maps to X)
                const x1 = startX + ((p1.lng - minLng) / lngRange) * width;
                const y1 = startY + height - ((p1.lat - minLat) / latRange) * height;

                const x2 = startX + ((p2.lng - minLng) / lngRange) * width;
                const y2 = startY + height - ((p2.lat - minLat) / latRange) * height;

                doc.line(x1, y1, x2, y2);
            }
        } else {
            doc.setFontSize(10);
            doc.setTextColor(100);
            doc.text("Not enough movement to visualize path.", startX + 5, startY + 10);
        }

        finalY += height + 15;
    }

    // High Risk Events Table
    if (stats.highRiskEvents.length > 0) {
        if (finalY > 250) { doc.addPage(); finalY = 20; }
        doc.setFontSize(14);
        doc.setTextColor(220, 38, 38); // Red
        doc.text("High Risk Events Log", 14, finalY);

        autoTable(doc, {
            startY: finalY + 5,
            head: [['Time', 'Risk', 'Location', 'Reason']],
            body: stats.highRiskEvents.map(e => [
                new Date(e.time).toLocaleTimeString(),
                `${e.risk.toFixed(0)}%`,
                `${e.lat.toFixed(5)}, ${e.lng.toFixed(5)}`,
                e.description
            ]),
            headStyles: { fillColor: [220, 38, 38] },
            styles: { fontSize: 9 },
        });
    } else {
        doc.setFontSize(12);
        doc.setTextColor(22, 163, 74); // Green
        doc.text("No High Risk Events Detected - Great Driving!", 14, finalY);
    }

    // Footer
    const pageCount = (doc as any).internal.getNumberOfPages();
    for (let i = 1; i <= pageCount; i++) {
        doc.setPage(i);
        doc.setFontSize(8);
        doc.setTextColor(150);
        doc.text(`Page ${i} of ${pageCount}`, 196, 285, { align: 'right' });
        doc.text("DriveGuard AI Fusion System", 14, 285);
    }

    doc.save(`Trip_Report_${now.toISOString().slice(0, 19).replace(/[:T]/g, '-')}.pdf`);
}
