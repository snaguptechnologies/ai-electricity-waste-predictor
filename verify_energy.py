import sqlite3
db = r'c:\Users\Admin\OneDrive\Desktop\New folder\ai-electricity-waste-predictor\electricity.db'
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row

print('Daily SUM (correct for increment schema) - last 7 days:')
q = 'SELECT date(timestamp) as day, SUM(energy_kwh) as daily_kwh, COUNT(*) as cnt FROM readings GROUP BY day ORDER BY day DESC LIMIT 7'
for r in conn.execute(q).fetchall():
    print(f"  {r['day']}  SUM={r['daily_kwh']:.3f} kWh  readings={r['cnt']}")

print()
r = conn.execute('SELECT SUM(energy_kwh) as total FROM readings').fetchone()
print(f"All-time total: {r['total']:.2f} kWh")

print()
print('30-day total:')
from datetime import datetime, timedelta
since = (datetime.utcnow() - timedelta(days=30)).isoformat()
r = conn.execute('SELECT SUM(energy_kwh) as total FROM readings WHERE timestamp >= ?', (since,)).fetchone()
print(f"  {r['total']:.2f} kWh")
conn.close()
