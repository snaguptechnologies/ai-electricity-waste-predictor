# AI Electricity Waste Predictor

> **Predict Energy. Detect Waste. Save Electricity.**

A college mini-project IoT analytics dashboard that monitors electricity usage, detects anomalies, predicts future consumption, calculates bills, and provides energy-saving recommendations.

---

## Features

| Feature | Status |
|---|---|
| Dashboard with live metric cards | ✅ Working |
| Daily / 24-hour charts (Chart.js) | ✅ Working |
| AI Prediction (LinearRegression / baseline) | ✅ Working |
| Waste / Anomaly Detection | ✅ Working |
| Electricity Bill Calculator | ✅ Working |
| Energy-Saving Recommendations | ✅ Working |
| Sensor Readings CRUD (add, search, sort, filter) | ✅ Working |
| CSV Export & Import | ✅ Working |
| SQLite database with 30-day sample data | ✅ Working |
| Settings persistence | ✅ Working |
| ThingSpeak integration (optional) | ✅ Demo mode / configurable |
| Responsive design (desktop, tablet, mobile) | ✅ Working |

---

## Quick Start

### 1. Install Python dependencies

```bash
cd ai-electricity-waste-predictor
pip install -r requirements.txt
```

### 2. (Optional) Configure ThingSpeak

Copy `.env.example` to `.env` and fill in your credentials:

```bash
copy .env.example .env
```

Edit `.env`:
```
THINGSPEAK_CHANNEL_ID=your_channel_id
THINGSPEAK_READ_API_KEY=your_read_api_key
```

Leave blank to run fully in **demo mode** with simulated data.

### 3. Run the server

```bash
python app.py
```

### 4. Open the app

Visit: **http://localhost:5000**

---

## Project Structure

```
ai-electricity-waste-predictor/
├── app.py                      # Flask application & API routes
├── requirements.txt
├── .env.example                # Environment variable template
├── .gitignore
├── README.md
├── database/
│   ├── __init__.py
│   └── init_db.py              # DB init, table creation, sample data seeding
├── services/
│   ├── __init__.py
│   ├── prediction_service.py   # ML prediction (LinearRegression / baseline)
│   ├── alert_service.py        # Threshold-based anomaly detection
│   └── thingspeak_service.py   # Optional ThingSpeak integration
├── templates/
│   └── index.html              # Single-page app (all 7 pages)
└── static/
    ├── css/
    │   └── style.css           # Dark-navy dashboard theme
    └── js/
        ├── app.js              # Navigation, API helpers, utilities
        └── dashboard.js        # Page-specific logic & Chart.js rendering
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Server health + DB count |
| GET | `/api/dashboard` | Dashboard summary data |
| GET | `/api/readings` | Paginated readings (search, filter, sort) |
| POST | `/api/readings` | Add a new reading |
| GET | `/api/readings/export` | Download readings as CSV |
| POST | `/api/readings/reset` | Restore 30-day sample data |
| GET | `/api/predictions` | Get stored predictions |
| POST | `/api/predict` | Run prediction model |
| GET | `/api/alerts` | Get alerts (filterable) |
| POST | `/api/alerts/:id/acknowledge` | Acknowledge an alert |
| GET | `/api/settings` | Get all settings |
| PUT | `/api/settings` | Update settings |
| GET | `/api/thingspeak/status` | ThingSpeak connection status |
| POST | `/api/thingspeak/sync` | Fetch & import ThingSpeak data |

---

## Hardware Integration (Future)

The project is designed for an **ESP32** with:
- ACS712 current sensor
- Voltage divider circuit
- OLED display, buzzer, LEDs

The ESP32 sends data to **ThingSpeak**. Configure the field mappings in Settings to match your channel.

**Important notes:**
- Apparent power (V×I) ≠ real power for AC loads (power factor ~0.8–0.95)
- Voltage anomaly ≠ electricity waste (they are separate alert types)
- Calibrate sensors before relying on measurements

---

## Prediction Model

- **≥7 days of data**: Linear Regression (scikit-learn) with day-index + day-of-week features, chronological train/test split
- **<7 days**: Moving-average baseline (clearly labelled)
- MAE is reported when a test set is available
- Predictions are estimates; not guaranteed to be accurate

---

## Technologies Used

- Python 3.10+, Flask, Flask-CORS
- SQLite (no external database needed)
- pandas, scikit-learn, numpy
- HTML5, CSS3, Vanilla JavaScript
- Chart.js 4.x
- Lucide-style SVG icons (inline)
- Google Fonts (Inter, JetBrains Mono)
