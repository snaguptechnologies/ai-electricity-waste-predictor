"""
AI Electricity Waste Predictor - Flask Backend
Run: py -3 app.py

energy_kwh in the database = kWh consumed IN THAT HOUR (hourly increment).
  Daily consumption  = SUM(energy_kwh) WHERE DATE(timestamp) = 'YYYY-MM-DD'
  30-day total       = SUM(energy_kwh) for last 30 days
  Estimated bill     = 30-day total * electricity_rate
"""
import os
import csv
import io
from datetime import datetime, timedelta

from flask import Flask, jsonify, request, render_template, Response
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()   # Must be before services that read env vars

from database.init_db import init_db, get_connection, reset_sample_data
from services.prediction_service import run_prediction
from services.alert_service import detect_and_store_alerts, get_alerts
from services import thingspeak_service as ts_svc

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")
CORS(app)

# ── Initialise DB on startup ──────────────────────────────────────────────────
init_db()


# ════════════════════════════════════════════════════════════════
#  FRONTEND
# ════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ════════════════════════════════════════════════════════════════
#  API ROUTES
# ════════════════════════════════════════════════════════════════

# ── Health ───────────────────────────────────────────────────────────────────
@app.route("/api/health")
def api_health():
    conn  = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    conn.close()
    return jsonify({
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "readings_count": count,
        "thingspeak_configured": ts_svc.is_configured(),
    })


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route("/api/dashboard")
def api_dashboard():
    conn = get_connection()

    # Latest reading (most recent sensor snapshot)
    latest = conn.execute(
        "SELECT * FROM readings ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()

    # Last 24 hours for charts
    since_24h = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    recent_24 = conn.execute(
        "SELECT * FROM readings WHERE timestamp >= ? ORDER BY timestamp ASC",
        (since_24h,)
    ).fetchall()

    # 30-day daily consumption: SUM(energy_kwh) per day
    # energy_kwh is an hourly increment so SUM gives daily kWh correctly
    since_30d = (datetime.utcnow() - timedelta(days=30)).isoformat()
    daily = conn.execute("""
        SELECT DATE(timestamp) as day,
               AVG(voltage)    as avg_v,
               AVG(current)    as avg_a,
               AVG(power)      as avg_w,
               SUM(energy_kwh) as daily_kwh
        FROM readings
        WHERE timestamp >= ?
        GROUP BY day
        ORDER BY day ASC
        LIMIT 31
    """, (since_30d,)).fetchall()

    # 30-day total consumption for bill
    total_kwh_30d_row = conn.execute(
        "SELECT SUM(energy_kwh) FROM readings WHERE timestamp >= ?",
        (since_30d,)
    ).fetchone()
    total_kwh_30d = float(total_kwh_30d_row[0] or 0)

    # All-time cumulative (meter total)
    meter_total_row = conn.execute("SELECT SUM(energy_kwh) FROM readings").fetchone()
    meter_total = float(meter_total_row[0] or 0)

    # 24-hour total
    kwh_24h_row = conn.execute(
        "SELECT SUM(energy_kwh) FROM readings WHERE timestamp >= ?",
        (since_24h,)
    ).fetchone()
    kwh_24h = float(kwh_24h_row[0] or 0)

    # Settings
    settings_rows = conn.execute("SELECT key, value FROM settings").fetchall()
    settings = {r["key"]: r["value"] for r in settings_rows}

    # Alerts (last 5)
    alerts = conn.execute(
        "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 5"
    ).fetchall()

    # Latest prediction
    pred = conn.execute(
        "SELECT * FROM predictions WHERE horizon='next_day' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()

    conn.close()

    rate           = float(settings.get("electricity_rate", 8.0))
    estimated_bill = round(total_kwh_30d * rate, 2)

    return jsonify({
        # Latest sensor snapshot
        "latest": dict(latest) if latest else {},

        # Energy summaries (clearly labelled)
        "kwh_last_24h":    round(kwh_24h, 3),
        "kwh_last_30d":    round(total_kwh_30d, 3),
        "meter_total_kwh": round(meter_total, 3),

        # Bill based on 30-day consumption
        "estimated_bill":        estimated_bill,
        "bill_period_days":      30,
        "bill_based_on_kwh":     round(total_kwh_30d, 3),

        # Prediction
        "predicted_next_day_kwh": pred["predicted_kwh"] if pred else None,
        "prediction_model":       pred["model_name"]    if pred else "Not run yet",

        # Charts
        "daily_stats": [dict(d) for d in daily],
        "recent_24h": [
            {
                "timestamp":  r["timestamp"],
                "voltage":    r["voltage"],
                "current":    r["current"],
                "power":      r["power"],
                "energy_kwh": r["energy_kwh"],
            }
            for r in recent_24
        ],

        # Other
        "alerts":              [dict(a) for a in alerts],
        "settings":            {k: v for k, v in settings.items()
                                if "api_key" not in k.lower()},
        "thingspeak_connected": ts_svc.is_configured(),
        "demo_mode":            settings.get("demo_mode", "true") == "true",
    })


# ── Readings ──────────────────────────────────────────────────────────────────
@app.route("/api/readings", methods=["GET"])
def api_get_readings():
    conn     = get_connection()
    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(200, max(1, int(request.args.get("per_page", 50))))
    search   = request.args.get("search", "").strip()
    start    = request.args.get("start_date", "")
    end      = request.args.get("end_date", "")
    sort_by  = request.args.get("sort_by", "timestamp")
    sort_dir = "DESC" if request.args.get("sort_dir", "desc").lower() == "desc" else "ASC"
    source   = request.args.get("source", "")

    allowed_cols = {"timestamp", "voltage", "current", "power", "energy_kwh", "source", "status"}
    if sort_by not in allowed_cols:
        sort_by = "timestamp"

    q      = "SELECT * FROM readings WHERE 1=1"
    params = []

    if search:
        q += " AND (device_id LIKE ? OR source LIKE ? OR status LIKE ?)"
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    if start:
        q += " AND timestamp >= ?"
        params.append(start)
    if end:
        q += " AND timestamp <= ?"
        params.append(end)
    if source:
        q += " AND source = ?"
        params.append(source)

    total = conn.execute(f"SELECT COUNT(*) FROM ({q})", params).fetchone()[0]
    q    += f" ORDER BY {sort_by} {sort_dir} LIMIT ? OFFSET ?"
    params += [per_page, (page - 1) * per_page]
    rows  = conn.execute(q, params).fetchall()
    conn.close()

    return jsonify({
        "readings": [dict(r) for r in rows],
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    max(1, (total + per_page - 1) // per_page),
    })


@app.route("/api/readings", methods=["POST"])
def api_add_reading():
    data   = request.get_json(force=True)
    errors = {}

    voltage    = data.get("voltage")
    current    = data.get("current")
    power      = data.get("power")
    energy_kwh = data.get("energy_kwh")
    device_id  = data.get("device_id", "ESP32-01")
    source     = data.get("source", "Manual")
    timestamp  = data.get("timestamp", datetime.utcnow().isoformat())[:19]

    # Type validation
    for field, val in [("voltage", voltage), ("current", current)]:
        try:
            float(val)
        except (TypeError, ValueError):
            errors[field] = f"{field} must be a number"

    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 400

    voltage = float(voltage)
    current = float(current)

    # Range checks
    if not (50 <= voltage <= 350):
        errors["voltage"] = "Voltage must be between 50 and 350 V"
    if not (0 <= current <= 100):
        errors["current"] = "Current must be between 0 and 100 A"
    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 400

    # Calculate power (real power with 0.9 power factor if not supplied)
    if power is not None:
        try:
            power = float(power)
        except (TypeError, ValueError):
            power = round(voltage * current * 0.9, 2)
    else:
        power = round(voltage * current * 0.9, 2)

    # energy_kwh = kWh for this 1-hour interval
    # If caller provides it, use it; otherwise estimate from power
    if energy_kwh is not None:
        try:
            energy_kwh = float(energy_kwh)
            if energy_kwh < 0:
                energy_kwh = round(power / 1000.0, 4)
        except (TypeError, ValueError):
            energy_kwh = round(power / 1000.0, 4)
    else:
        # Assume 1-hour interval; power in W / 1000 = kWh
        energy_kwh = round(power / 1000.0, 4)

    # Determine anomaly status
    conn      = get_connection()
    baseline  = float(conn.execute(
        "SELECT value FROM settings WHERE key='voltage_baseline'"
    ).fetchone()["value"])
    threshold = float(conn.execute(
        "SELECT value FROM settings WHERE key='voltage_threshold'"
    ).fetchone()["value"])
    dev    = abs(voltage - baseline) / baseline * 100
    status = "Anomaly" if dev > threshold else "Normal"

    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO readings
                (timestamp, voltage, current, power, energy_kwh, device_id, source, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, voltage, current, power, energy_kwh,
              device_id, source, status))
        conn.commit()
        reading_id = cur.lastrowid
        conn.close()
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500

    reading = {
        "id": reading_id, "timestamp": timestamp,
        "voltage": voltage, "current": current,
        "power": power, "energy_kwh": energy_kwh,
        "device_id": device_id, "source": source, "status": status,
    }
    detect_and_store_alerts(reading)
    return jsonify({"success": True, "reading": reading}), 201


@app.route("/api/readings/export", methods=["GET"])
def api_export_csv():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM readings ORDER BY timestamp ASC"
    ).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "timestamp", "voltage", "current", "power",
        "energy_kwh_increment", "device_id", "source", "status"
    ])
    for r in rows:
        writer.writerow([
            r["id"], r["timestamp"], r["voltage"], r["current"],
            r["power"], r["energy_kwh"], r["device_id"], r["source"], r["status"]
        ])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=readings.csv"}
    )


@app.route("/api/readings/reset", methods=["POST"])
def api_reset_data():
    reset_sample_data()
    return jsonify({"success": True, "message": "30-day sample data restored."})


# ── Predictions ───────────────────────────────────────────────────────────────
@app.route("/api/predictions", methods=["GET"])
def api_get_predictions():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM predictions ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/predict", methods=["POST"])
def api_predict():
    result = run_prediction()
    return jsonify(result)


# ── Alerts ────────────────────────────────────────────────────────────────────
@app.route("/api/alerts", methods=["GET"])
def api_get_alerts():
    severity   = request.args.get("severity", "")
    start_date = request.args.get("start_date", "")
    end_date   = request.args.get("end_date", "")
    limit      = min(500, max(1, int(request.args.get("limit", 100))))
    alerts = get_alerts(
        limit=limit,
        severity=severity or None,
        start_date=start_date or None,
        end_date=end_date or None,
    )
    return jsonify(alerts)


@app.route("/api/alerts/<int:alert_id>/acknowledge", methods=["POST"])
def api_acknowledge_alert(alert_id):
    conn = get_connection()
    conn.execute("UPDATE alerts SET acknowledged=1 WHERE id=?", (alert_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ── Settings ──────────────────────────────────────────────────────────────────
@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    conn = get_connection()
    rows = conn.execute("SELECT key, value, label FROM settings").fetchall()
    conn.close()
    safe = {
        r["key"]: {"value": r["value"], "label": r["label"]}
        for r in rows
        if "api_key" not in r["key"].lower()
    }
    return jsonify(safe)


@app.route("/api/settings", methods=["PUT"])
def api_update_settings():
    data    = request.get_json(force=True)
    conn    = get_connection()
    now     = datetime.utcnow().isoformat()
    allowed = {
        "electricity_rate", "voltage_baseline", "voltage_threshold",
        "consec_threshold", "demo_mode", "thingspeak_interval",
        "field_voltage", "field_current", "field_power", "field_energy",
    }
    updated = []
    for key, value in data.items():
        if key in allowed:
            conn.execute(
                "UPDATE settings SET value=?, updated_at=? WHERE key=?",
                (str(value), now, key)
            )
            updated.append(key)
    conn.commit()
    conn.close()
    return jsonify({"success": True, "updated": updated})


# ── ThingSpeak ────────────────────────────────────────────────────────────────
@app.route("/api/thingspeak/status", methods=["GET"])
def api_thingspeak_status():
    return jsonify(ts_svc.connection_status())


@app.route("/api/thingspeak/sync", methods=["POST"])
def api_thingspeak_sync():
    result = ts_svc.sync_to_db(results=200)
    return jsonify(result)


# ════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    port  = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    print(f"\n{'='*55}")
    print(f"  AI Electricity Waste Predictor")
    print(f"  Running on  : http://localhost:{port}")
    print(f"  Demo mode   : {not ts_svc.is_configured()}")
    print(f"  energy_kwh  : hourly increment (kWh per reading)")
    print(f"{'='*55}\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
