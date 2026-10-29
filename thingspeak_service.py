"""
ThingSpeak integration service.
Reads credentials from environment variables only – never from the browser.
If credentials are missing, all methods return a 'disconnected' status so the
application continues to work in demo mode.
"""
import os
import requests
from datetime import datetime
from database.init_db import get_connection

# Load env (dotenv loaded in app.py before this module is imported)
CHANNEL_ID   = os.getenv("THINGSPEAK_CHANNEL_ID", "").strip()
READ_API_KEY = os.getenv("THINGSPEAK_READ_API_KEY", "").strip()
BASE_URL     = "https://api.thingspeak.com"


def is_configured() -> bool:
    return bool(CHANNEL_ID and READ_API_KEY)


def _field_map():
    """Return configurable field → column mapping from env / settings."""
    conn = get_connection()
    def gs(k, d):
        r = conn.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
        return r["value"] if r else d
    mapping = {
        "voltage": gs("field_voltage", "field1"),
        "current": gs("field_current", "field2"),
        "power":   gs("field_power",   "field3"),
        "energy":  gs("field_energy",  "field4"),
    }
    conn.close()
    return mapping


def fetch_latest():
    if not is_configured():
        return {"status": "disconnected", "message": "ThingSpeak credentials not configured."}

    url = f"{BASE_URL}/channels/{CHANNEL_ID}/feeds/last.json"
    try:
        resp = requests.get(url, params={"api_key": READ_API_KEY}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return _parse_feed(data, "latest")
    except requests.RequestException as e:
        return {"status": "error", "message": str(e)}


def fetch_historical(results=100):
    if not is_configured():
        return {"status": "disconnected", "feeds": [], "count": 0}

    url = f"{BASE_URL}/channels/{CHANNEL_ID}/feeds.json"
    try:
        resp = requests.get(url, params={"api_key": READ_API_KEY, "results": results}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        feeds = data.get("feeds", [])
        parsed = [_parse_feed(f, "ThingSpeak") for f in feeds]
        return {"status": "ok", "feeds": parsed, "count": len(parsed)}
    except requests.RequestException as e:
        return {"status": "error", "feeds": [], "message": str(e)}


def _parse_feed(feed: dict, source: str) -> dict:
    fm = _field_map()
    def safe_float(val):
        try: return float(val)
        except (TypeError, ValueError): return None

    return {
        "timestamp": feed.get("created_at", datetime.utcnow().isoformat()),
        "voltage":   safe_float(feed.get(fm["voltage"])),
        "current":   safe_float(feed.get(fm["current"])),
        "power":     safe_float(feed.get(fm["power"])),
        "energy_kwh":safe_float(feed.get(fm["energy"])),
        "device_id": f"TS-{CHANNEL_ID}",
        "source":    "ThingSpeak",
        "status":    "Normal",
    }


def sync_to_db(results=100):
    """Fetch ThingSpeak data and store new readings in SQLite (skips duplicates)."""
    fetched = fetch_historical(results)
    if fetched["status"] != "ok":
        return fetched

    conn = get_connection()
    cur  = conn.cursor()
    inserted = 0
    for feed in fetched["feeds"]:
        if any(v is None for v in [feed["voltage"], feed["current"]]):
            continue
        try:
            power = feed["power"] if feed["power"] is not None else round(feed["voltage"] * feed["current"] * 0.9, 2)
            energy = feed["energy_kwh"] if feed["energy_kwh"] is not None else 0.0
            cur.execute("""
                INSERT OR IGNORE INTO readings
                    (timestamp, voltage, current, power, energy_kwh, device_id, source, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (feed["timestamp"], feed["voltage"], feed["current"],
                  power, energy, feed["device_id"], "ThingSpeak", "Normal"))
            inserted += cur.rowcount
        except Exception as e:
            print(f"[ThingSpeak] Insert error: {e}")
    conn.commit()
    conn.close()
    return {"status": "ok", "inserted": inserted, "fetched": fetched["count"]}


def connection_status():
    if not is_configured():
        return {"connected": False, "reason": "Credentials not configured (demo mode)."}
    result = fetch_latest()
    if result.get("status") == "error":
        return {"connected": False, "reason": result.get("message", "Unknown error")}
    return {"connected": True, "last_reading": result}
