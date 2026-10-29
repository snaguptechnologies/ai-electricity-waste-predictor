"""
Database audit script - inspects data quality issues.
Run: py -3 tests/audit_db.py
"""
import sqlite3, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "electricity.db")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

print("=" * 60)
print("DATABASE AUDIT REPORT")
print("=" * 60)

# Basic counts
r = conn.execute("SELECT COUNT(*), MIN(energy_kwh), MAX(energy_kwh), MIN(timestamp), MAX(timestamp) FROM readings").fetchone()
print(f"\nTotal readings  : {r[0]}")
print(f"Energy range    : {r[1]:.4f} -> {r[2]:.4f} kWh")
print(f"Timestamp range : {r[3]} -> {r[4]}")

# Last 5 readings
print("\nLast 5 readings:")
for row in conn.execute("SELECT timestamp, voltage, current, power, energy_kwh, source FROM readings ORDER BY timestamp DESC LIMIT 5").fetchall():
    print(f"  {row['timestamp']}  V={row['voltage']:.1f}  A={row['current']:.3f}  W={row['power']:.1f}  kWh={row['energy_kwh']:.4f}  [{row['source']}]")

# Daily energy (MAX-MIN per day)
print("\nDaily energy (MAX-MIN) - last 7 days:")
daily_q = """
    SELECT date(timestamp) day,
           MAX(energy_kwh) - MIN(energy_kwh) as daily_kwh,
           COUNT(*) cnt
    FROM readings
    GROUP BY date(timestamp)
    ORDER BY day DESC
    LIMIT 7
"""
for row in conn.execute(daily_q).fetchall():
    print(f"  {row['day']}  daily_kwh={row['daily_kwh']:.4f}  readings={row['cnt']}")

# Check for the spike
print("\nChecking for spike days (daily_kwh > 20):")
spike_q = """
    SELECT date(timestamp) day,
           MAX(energy_kwh) - MIN(energy_kwh) as daily_kwh,
           MIN(energy_kwh) min_e, MAX(energy_kwh) max_e
    FROM readings
    GROUP BY date(timestamp)
    HAVING daily_kwh > 20
    ORDER BY day
"""
spikes = conn.execute(spike_q).fetchall()
if spikes:
    for row in spikes:
        print(f"  SPIKE: {row['day']}  daily_kwh={row['daily_kwh']:.2f}  (min={row['min_e']:.2f}, max={row['max_e']:.2f})")
else:
    print("  No spike days found (all <= 20 kWh/day)")

# Check energy_kwh is cumulative
print("\nFirst 5 readings (chronological) to verify cumulative energy:")
for row in conn.execute("SELECT timestamp, energy_kwh FROM readings ORDER BY timestamp ASC LIMIT 5").fetchall():
    print(f"  {row['timestamp']}  energy_kwh={row['energy_kwh']:.4f}")

# Check latest reading energy
latest = conn.execute("SELECT * FROM readings ORDER BY timestamp DESC LIMIT 1").fetchone()
print(f"\nLatest reading energy_kwh: {latest['energy_kwh']:.4f} (this is the cumulative meter total)")

# Check alerts
alert_counts = conn.execute("SELECT severity, COUNT(*) cnt FROM alerts GROUP BY severity").fetchall()
print(f"\nAlerts by severity: {[(r['severity'], r['cnt']) for r in alert_counts]}")

# Check settings
print("\nKey settings:")
for row in conn.execute("SELECT key, value FROM settings WHERE key IN ('electricity_rate','voltage_baseline','voltage_threshold','demo_mode')").fetchall():
    print(f"  {row['key']}: {row['value']}")

conn.close()
print("\n" + "=" * 60)
print("AUDIT COMPLETE")
print("=" * 60)
