"""
Database initialization and helper functions for AI Electricity Waste Predictor.

energy_kwh column meaning:
  Each reading stores the kWh consumed DURING THAT HOUR (hourly increment),
  NOT a cumulative meter total.

  This makes aggregation straightforward:
    Daily consumption  = SUM(energy_kwh) WHERE DATE(timestamp) = day
    Monthly total      = SUM(energy_kwh) WHERE timestamp >= month_start
    Meter reading total= SUM(energy_kwh) (all time)

  When real ESP32/ThingSpeak data sends cumulative meter readings,
  the ThingSpeak service converts them to increments before storing.
"""
import sqlite3
import os
import random
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "electricity.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # ── Readings ─────────────────────────────────────────────────────────────
    # energy_kwh = kWh consumed DURING THIS READING INTERVAL (hourly increment)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            voltage     REAL NOT NULL,
            current     REAL NOT NULL,
            power       REAL NOT NULL,
            energy_kwh  REAL NOT NULL DEFAULT 0,
            device_id   TEXT DEFAULT 'ESP32-01',
            source      TEXT DEFAULT 'Simulated',
            status      TEXT DEFAULT 'Normal',
            UNIQUE(timestamp, device_id)
        )
    """)

    # ── Predictions ──────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at      TEXT NOT NULL,
            horizon         TEXT NOT NULL,
            predicted_kwh   REAL NOT NULL,
            actual_kwh      REAL,
            model_name      TEXT DEFAULT 'Baseline',
            mae             REAL,
            notes           TEXT
        )
    """)

    # ── Alerts ───────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL,
            alert_type      TEXT NOT NULL,
            severity        TEXT NOT NULL,
            measured_value  REAL,
            expected_value  REAL,
            deviation_pct   REAL,
            explanation     TEXT,
            action          TEXT,
            acknowledged    INTEGER DEFAULT 0
        )
    """)

    # ── Settings ─────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key     TEXT PRIMARY KEY,
            value   TEXT NOT NULL,
            label   TEXT,
            updated_at TEXT
        )
    """)

    conn.commit()

    # Seed default settings
    _seed_settings(cur, conn)

    # Seed sample readings if table is empty
    count = cur.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    if count == 0:
        seed_sample_data(cur, conn)

    conn.close()
    print(f"[DB] Initialised -> {DB_PATH}")


def _seed_settings(cur, conn):
    defaults = [
        ("electricity_rate",    "8.0",   "Electricity Rate (Rs/kWh)"),
        ("voltage_baseline",    "230.0", "Voltage Baseline (V)"),
        ("voltage_threshold",   "4.0",   "Voltage Anomaly Threshold (%)"),
        ("consec_threshold",    "3",     "Consecutive Readings Before Alert"),
        ("demo_mode",           "true",  "Demo Mode"),
        ("thingspeak_enabled",  "false", "ThingSpeak Integration"),
        ("thingspeak_interval", "60",    "ThingSpeak Fetch Interval (s)"),
        ("field_voltage",       "field1","ThingSpeak Voltage Field"),
        ("field_current",       "field2","ThingSpeak Current Field"),
        ("field_power",         "field3","ThingSpeak Power Field"),
        ("field_energy",        "field4","ThingSpeak Energy Field"),
    ]
    now = datetime.utcnow().isoformat()
    for key, value, label in defaults:
        cur.execute("""
            INSERT OR IGNORE INTO settings (key, value, label, updated_at)
            VALUES (?, ?, ?, ?)
        """, (key, value, label, now))
    conn.commit()


def seed_sample_data(cur, conn):
    """
    Generate ~30 days of realistic hourly readings.

    energy_kwh stores the kWh consumed IN THAT HOUR (increment),
    so that SUM(energy_kwh) per day = daily consumption.

    Typical daily consumption: ~14-16 kWh (a medium household in India).
    """
    random.seed(42)
    base_ts = datetime.utcnow().replace(
        minute=0, second=0, microsecond=0
    ) - timedelta(days=30)

    rows = []
    for h in range(30 * 24):
        ts   = base_ts + timedelta(hours=h)
        hour = ts.hour

        # Voltage: nominal 230 V ± small variation; rare anomaly spike
        v_noise = random.gauss(0, 1.5)
        if random.random() < 0.02:          # ~2% chance of anomaly
            v_noise += random.choice([12, -12])
        voltage = round(230 + v_noise, 2)

        # Current profile by hour of day
        if   6 <= hour <  9:  base_a = 4.5   # morning peak
        elif 17 <= hour < 22: base_a = 5.5   # evening peak
        elif 23 <= hour or hour < 5: base_a = 0.8  # night low
        else:                 base_a = 2.5   # daytime normal

        current    = round(max(0.1, random.gauss(base_a, 0.4)), 3)
        # Apparent power; apply 0.9 power factor for real power
        real_power = round(voltage * current * 0.9, 2)
        # kWh for this 1-hour interval = real_power (W) / 1000
        energy_inc = round(real_power / 1000.0, 4)

        # Anomaly detection
        baseline = 230.0
        dev      = abs(voltage - baseline) / baseline * 100
        status   = "Anomaly" if dev > 4 else "Normal"

        rows.append((
            ts.strftime("%Y-%m-%dT%H:%M:%S"),
            voltage, current, real_power,
            energy_inc,          # <<< hourly increment, NOT cumulative
            "ESP32-01", "Simulated", status
        ))

    cur.executemany("""
        INSERT OR IGNORE INTO readings
            (timestamp, voltage, current, power, energy_kwh, device_id, source, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    # Seed alerts from anomaly readings
    alert_rows = []
    for ts, v, _, _, _, _, _, status in rows:
        if status == "Anomaly":
            baseline = 230.0
            dev      = round((v - baseline) / baseline * 100, 2)
            sev      = "High" if abs(dev) > 8 else ("Medium" if abs(dev) > 5 else "Low")
            direction = "above" if dev > 0 else "below"
            alert_rows.append((
                ts, "Voltage Anomaly", sev, v, baseline, dev,
                f"Voltage is {abs(dev):.1f}% {direction} the {baseline} V baseline. "
                f"Note: a voltage deviation alone does not confirm electricity waste.",
                "Check power supply connections. If recurring, consult an electrician."
            ))
        if len(alert_rows) >= 20:
            break

    cur.executemany("""
        INSERT INTO alerts
            (timestamp, alert_type, severity, measured_value, expected_value,
             deviation_pct, explanation, action)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, alert_rows)

    conn.commit()
    total_kwh = sum(r[4] for r in rows)
    print(f"[DB] Seeded {len(rows)} hourly readings | "
          f"Total energy: {total_kwh:.1f} kWh | "
          f"Alerts: {len(alert_rows)}")


def reset_sample_data():
    """Delete all readings/alerts/predictions and re-seed sample data."""
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM readings")
    cur.execute("DELETE FROM alerts")
    cur.execute("DELETE FROM predictions")
    conn.commit()
    seed_sample_data(cur, conn)
    conn.close()
    print("[DB] Sample data reset complete.")


if __name__ == "__main__":
    init_db()
