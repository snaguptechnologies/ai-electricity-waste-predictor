"""
Alert / anomaly-detection service.
Uses threshold-based detection matching the ESP32 firmware logic:
  - Voltage baseline learned from valid readings
  - Configurable deviation threshold (default 4 %)
  - Unusual power consumption detection
Voltage anomalies and high-consumption events are reported as separate alert types.
"""
from datetime import datetime
from database.init_db import get_connection


def _get_setting(key, default):
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return float(row["value"]) if row else default


def detect_and_store_alerts(reading: dict) -> list:
    """
    Analyse a single reading dict and create alerts if thresholds are breached.
    Returns list of newly created alert dicts.
    """
    voltage   = reading.get("voltage", 230)
    power     = reading.get("power", 0)
    timestamp = reading.get("timestamp", datetime.utcnow().isoformat())

    baseline  = _get_setting("voltage_baseline",  230.0)
    threshold = _get_setting("voltage_threshold",   4.0)

    alerts = []

    # ── Voltage anomaly ──────────────────────────────────────────────────────
    dev_pct = (voltage - baseline) / baseline * 100
    if abs(dev_pct) > threshold:
        sev = "High" if abs(dev_pct) > 8 else ("Medium" if abs(dev_pct) > 5 else "Low")
        direction = "high" if dev_pct > 0 else "low"
        explanation = (
            f"Voltage is {abs(round(dev_pct,1))}% {direction} of the {baseline} V baseline. "
            f"This may indicate supply fluctuations or a measurement spike."
        )
        action = (
            "Check power supply connections. If recurring, consult an electrician. "
            "Note: a voltage deviation alone does not confirm electricity waste."
        )
        alerts.append(_store_alert(timestamp, "Voltage Anomaly", sev, voltage, baseline, dev_pct, explanation, action))

    # ── High power consumption ───────────────────────────────────────────────
    HIGH_POWER_W = 1500   # simple fixed threshold; tune per installation
    if power > HIGH_POWER_W:
        sev = "High" if power > 3000 else "Medium"
        explanation = (
            f"Instantaneous power ({round(power,1)} W) exceeds {HIGH_POWER_W} W. "
            f"High-load devices such as air conditioners, geysers, or heaters may be active."
        )
        action = (
            "Identify which devices are running. Switch off unused high-power equipment. "
            "Consider scheduling heavy loads during off-peak hours."
        )
        dev_pct_p = round((power - HIGH_POWER_W) / HIGH_POWER_W * 100, 2)
        alerts.append(_store_alert(timestamp, "High Power Consumption", sev, power, HIGH_POWER_W, dev_pct_p, explanation, action))

    return [a for a in alerts if a]


def _store_alert(timestamp, alert_type, severity, measured, expected, dev_pct, explanation, action):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO alerts
                (timestamp, alert_type, severity, measured_value, expected_value,
                 deviation_pct, explanation, action)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, alert_type, severity, measured, expected, round(dev_pct, 2), explanation, action))
        conn.commit()
        alert_id = cur.lastrowid
        conn.close()
        return {
            "id": alert_id, "timestamp": timestamp,
            "alert_type": alert_type, "severity": severity,
            "measured_value": measured, "expected_value": expected,
            "deviation_pct": round(dev_pct, 2),
            "explanation": explanation, "action": action
        }
    except Exception as e:
        print(f"[AlertService] Error storing alert: {e}")
        return None


def get_alerts(limit=100, severity=None, start_date=None, end_date=None):
    conn = get_connection()
    query = "SELECT * FROM alerts WHERE 1=1"
    params = []
    if severity:
        query += " AND severity=?"
        params.append(severity)
    if start_date:
        query += " AND timestamp >= ?"
        params.append(start_date)
    if end_date:
        query += " AND timestamp <= ?"
        params.append(end_date)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
