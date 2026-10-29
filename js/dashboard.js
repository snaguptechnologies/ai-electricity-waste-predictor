/**
 * dashboard.js – All page-specific logic for the AI Electricity Waste Predictor
 * Pages: Dashboard, Predictions, Alerts, Calculator, Recommendations, Readings, Settings
 */

// Stored chart instances to allow re-rendering
const charts = {};

// ════════════════════════════════════════════════════════════════
//  DASHBOARD
// ════════════════════════════════════════════════════════════════
async function loadDashboard() {
  try {
    const data = await apiFetch('/dashboard');
    renderMetricCards(data);
    renderDashboardCharts(data);
    renderRecentReadingsTable(data.recent_24h || []);
    renderDashboardAlerts(data.alerts || []);
    renderDashboardRecommendations();
    updateThingSpeakStatus(data.thingspeak_connected);
  } catch (e) {
    showToast('Failed to load dashboard: ' + e.message, 'error');
  }
}

function renderMetricCards(data) {
  const latest = data.latest || {};
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };
  // Latest sensor snapshot
  set('m-voltage', fmt(latest.voltage, 1) + ' V');
  set('m-current', fmt(latest.current, 2) + ' A');
  set('m-power',   fmt(latest.power,   1) + ' W');

  // Energy consumed in last 30 days (SUM of hourly increments)
  set('m-energy',  fmt(data.kwh_last_30d, 2) + ' kWh');

  // Bill based on 30-day consumption
  set('m-bill',    '\u20B9 ' + fmt(data.estimated_bill, 2));

  // Prediction
  set('m-predicted', data.predicted_next_day_kwh != null
    ? fmt(data.predicted_next_day_kwh, 3) + ' kWh'
    : 'Click Predictions');

  // Status & meta
  set('m-status',  latest.status || 'No data');
  set('m-updated', fmtDate(latest.timestamp));
  set('m-model',   data.prediction_model || 'Not run yet');

  // Update subtitles
  const billSub = document.getElementById('m-bill-sub');
  if (billSub) billSub.textContent = `Based on ${fmt(data.kwh_last_30d, 1)} kWh (30 days)`;

  const energySub = document.getElementById('m-energy-sub');
  if (energySub) energySub.textContent = `24h: ${fmt(data.kwh_last_24h, 2)} kWh`;

  // Colour the status
  const statusEl = document.getElementById('m-status');
  if (statusEl) {
    statusEl.style.color = latest.status === 'Anomaly' ? 'var(--red)' : 'var(--green)';
  }
}

function renderDashboardCharts(data) {
  const daily  = data.daily_stats || [];
  const recent = data.recent_24h  || [];

  // Daily energy chart – each bar = SUM(hourly increments) for that day
  // Filter out any day where daily_kwh looks unrealistic (> 100 kWh)
  const validDaily = daily.filter(d => d.daily_kwh != null && d.daily_kwh >= 0 && d.daily_kwh <= 100);
  renderLineChart('chart-daily-energy', {
    labels: validDaily.map(d => d.day ? fmtShortDate(d.day) : ''),
    datasets: [{
      label: 'Daily Consumption (kWh)',
      data: validDaily.map(d => d.daily_kwh),
      borderColor: '#00d4ff',
      backgroundColor: ctx => chartGradient(ctx.chart.ctx, 'rgba(0,212,255,0.3)', 'rgba(0,212,255,0)'),
      ...CHART_DEFAULTS,
    }]
  }, {
    plugins: {
      tooltip: {
        callbacks: {
          label: ctx => ` ${fmt(ctx.parsed.y, 2)} kWh consumed`
        }
      }
    }
  });

  // Time labels helper
  const toTimeLabel = ts => {
    const d = new Date(ts.replace('T',' ') + ' UTC');
    return d.toLocaleTimeString('en-IN', {hour:'2-digit', minute:'2-digit', hour12:false});
  };

  // Voltage history (last 24h) with 230V baseline reference
  renderLineChart('chart-voltage', {
    labels: recent.map(r => toTimeLabel(r.timestamp)),
    datasets: [
      {
        label: 'Voltage (V)',
        data: recent.map(r => r.voltage),
        borderColor: '#f59e0b',
        backgroundColor: ctx => chartGradient(ctx.chart.ctx, 'rgba(245,158,11,0.2)', 'rgba(245,158,11,0)'),
        ...CHART_DEFAULTS,
      },
      {
        label: 'Baseline (230V)',
        data: recent.map(() => 230),
        borderColor: 'rgba(100,116,139,0.5)',
        borderDash: [6, 3],
        borderWidth: 1,
        pointRadius: 0,
        fill: false,
        tension: 0,
      }
    ]
  });

  // Power & Current chart (last 24h)
  renderLineChart('chart-power', {
    labels: recent.map(r => toTimeLabel(r.timestamp)),
    datasets: [
      {
        label: 'Power (W)',
        data: recent.map(r => r.power),
        borderColor: '#3b82f6',
        backgroundColor: ctx => chartGradient(ctx.chart.ctx, 'rgba(59,130,246,0.25)', 'rgba(59,130,246,0)'),
        ...CHART_DEFAULTS,
      },
      {
        label: 'Current ×100 (A scaled)',
        data: recent.map(r => (r.current || 0) * 100),
        borderColor: '#10b981',
        backgroundColor: 'transparent',
        borderDash: [4, 3],
        fill: false,
        ...CHART_DEFAULTS,
      }
    ]
  });
}

function renderRecentReadingsTable(readings) {
  const tbody = document.getElementById('dash-readings-tbody');
  if (!tbody) return;
  const rows = readings.slice(-10).reverse();
  tbody.innerHTML = rows.length ? rows.map(r => `
    <tr>
      <td class="mono" style="color:var(--text-muted);font-size:11px">${fmtDate(r.timestamp)}</td>
      <td class="mono">${fmt(r.voltage,1)}</td>
      <td class="mono">${fmt(r.current,3)}</td>
      <td class="mono">${fmt(r.power,1)}</td>
      <td class="mono">${fmt(r.energy_kwh,4)}</td>
    </tr>
  `).join('') : '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">No data</td></tr>';
}

function renderDashboardAlerts(alerts) {
  const el = document.getElementById('dash-alerts');
  if (!el) return;
  el.innerHTML = alerts.length ? alerts.map(a => `
    <div class="alert-item">
      <div class="alert-dot ${(a.severity||'').toLowerCase()}"></div>
      <div class="alert-content">
        <div class="alert-title">${a.alert_type}</div>
        <div class="alert-desc">${a.explanation || ''}</div>
        <div class="alert-meta">
          ${severityBadge(a.severity)}
          <span>${fmtDate(a.timestamp)}</span>
          ${a.measured_value != null ? `<span>Measured: ${fmt(a.measured_value,2)}</span>` : ''}
        </div>
      </div>
    </div>
  `).join('') : '<p style="color:var(--text-muted);font-size:13px">No recent alerts.</p>';
}

function renderDashboardRecommendations() {
  const el = document.getElementById('dash-recs');
  if (!el) return;
  const recs = getRecommendationData().slice(0, 4);
  el.innerHTML = recs.map(r => `
    <div class="rec-item">
      <div class="rec-icon" style="background:${r.iconBg}">${r.icon}</div>
      <div>
        <div class="rec-title">${r.title}</div>
        <div class="rec-desc">${r.desc}</div>
        ${r.saving ? `<div class="rec-saving">${r.saving}</div>` : ''}
      </div>
    </div>
  `).join('');
}

function updateThingSpeakStatus(connected) {
  const el = document.getElementById('ts-status');
  if (!el) return;
  el.className = 'status-chip ' + (connected ? 'online' : 'demo');
  el.innerHTML = `<div class="dot"></div>${connected ? 'ThingSpeak Connected' : 'Demo Mode'}`;
}

// ── Generic line chart renderer ──────────────────────────────────────────────
function renderLineChart(canvasId, chartData, extraOpts = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  if (charts[canvasId]) { charts[canvasId].destroy(); }
  const baseOptions = {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: chartData.datasets.length > 1, labels: { boxWidth: 10, padding: 12 } },
      tooltip: { backgroundColor: '#111827', borderColor: '#1e2d45', borderWidth: 1 },
    },
    scales: {
      x: { grid: { color: '#1e2d45' }, ticks: { maxTicksLimit: 8 } },
      y: { grid: { color: '#1e2d45' } },
    },
  };
  // Deep-merge extraOpts into baseOptions (plugins level)
  if (extraOpts.plugins) {
    Object.assign(baseOptions.plugins, extraOpts.plugins);
    if (extraOpts.plugins.tooltip) {
      Object.assign(baseOptions.plugins.tooltip, extraOpts.plugins.tooltip);
    }
  }
  charts[canvasId] = new Chart(canvas, {
    type: 'line',
    data: chartData,
    options: baseOptions,
  });
}

function renderBarChart(canvasId, chartData, opts = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  if (charts[canvasId]) { charts[canvasId].destroy(); }
  charts[canvasId] = new Chart(canvas, {
    type: 'bar',
    data: chartData,
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: chartData.datasets.length > 1, labels: { boxWidth: 10 } },
        tooltip: { backgroundColor: '#111827', borderColor: '#1e2d45', borderWidth: 1 },
      },
      scales: {
        x: { grid: { color: '#1e2d45' }, ticks: { maxTicksLimit: 10 } },
        y: { grid: { color: '#1e2d45' } },
      },
      ...opts,
    },
  });
}

// ════════════════════════════════════════════════════════════════
//  PREDICTIONS
// ════════════════════════════════════════════════════════════════
async function loadPredictions() {
  try {
    const data = await apiFetch('/predict', { method: 'POST' });
    renderPredictionPage(data);
  } catch (e) {
    // Try loading cached predictions
    try {
      const cached = await apiFetch('/predictions');
      if (cached.length) renderPredictionPageCached(cached[0]);
    } catch (_) {}
    showToast('Prediction error: ' + e.message, 'error');
  }
}

function renderPredictionPage(data) {
  document.getElementById('pred-model-name').textContent = data.model_name || 'Unknown';
  document.getElementById('pred-trained').textContent = data.trained ? '✓ ML Model Trained' : '⚠ Baseline Method';
  document.getElementById('pred-trained').style.color = data.trained ? 'var(--green)' : 'var(--yellow)';
  document.getElementById('pred-next-hour').textContent = data.next_hour_kwh != null ? fmt(data.next_hour_kwh, 4) + ' kWh' : '—';
  document.getElementById('pred-next-day').textContent  = data.next_day_kwh  != null ? fmt(data.next_day_kwh,  4) + ' kWh' : '—';
  document.getElementById('pred-data-pts').textContent  = (data.data_points || 0) + ' days';
  document.getElementById('pred-mae').textContent = data.mae != null ? fmt(data.mae, 4) + ' kWh' : 'N/A';
  document.getElementById('pred-notes').textContent = data.notes || '';

  // Actual vs Predicted chart
  const avp = data.actual_vs_predicted || [];
  if (avp.length) {
    renderLineChart('chart-avp', {
      labels: avp.map(d => d.date),
      datasets: [
        {
          label: 'Actual (kWh)',
          data: avp.map(d => d.actual),
          borderColor: '#00d4ff',
          backgroundColor: ctx => chartGradient(ctx.chart.ctx, 'rgba(0,212,255,0.2)', 'rgba(0,212,255,0)'),
          ...CHART_DEFAULTS,
        },
        {
          label: 'Predicted (kWh)',
          data: avp.map(d => d.predicted),
          borderColor: '#f59e0b',
          borderDash: [5, 3],
          backgroundColor: 'transparent',
          fill: false,
          ...CHART_DEFAULTS,
        }
      ]
    });
  }

  // 7-day forecast chart
  const fc = data.seven_day_forecast || [];
  if (fc.length) {
    renderBarChart('chart-forecast', {
      labels: fc.map(d => d.date),
      datasets: [{
        label: '7-Day Forecast (kWh)',
        data: fc.map(d => d.predicted_kwh),
        backgroundColor: fc.map((_, i) =>
          i === 0 ? 'rgba(0,212,255,0.8)' : 'rgba(59,130,246,0.5)'
        ),
        borderColor: '#3b82f6',
        borderWidth: 1,
        borderRadius: 6,
      }]
    });
  }
}

function renderPredictionPageCached(pred) {
  document.getElementById('pred-model-name').textContent = pred.model_name || 'Unknown';
  document.getElementById('pred-next-day').textContent = fmt(pred.predicted_kwh, 4) + ' kWh';
  document.getElementById('pred-mae').textContent = pred.mae != null ? fmt(pred.mae, 4) : 'N/A';
  document.getElementById('pred-notes').textContent = pred.notes || '';
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('btn-refresh-pred')?.addEventListener('click', async () => {
    showToast('Running prediction...', 'info');
    await loadPredictions();
    showToast('Prediction updated', 'success');
  });
});

// ════════════════════════════════════════════════════════════════
//  ALERTS
// ════════════════════════════════════════════════════════════════
let alertsData = [];

async function loadAlerts() {
  try {
    const params = new URLSearchParams();
    const sev    = document.getElementById('filter-severity')?.value;
    const start  = document.getElementById('filter-start')?.value;
    const end    = document.getElementById('filter-end')?.value;
    if (sev)   params.set('severity',   sev);
    if (start) params.set('start_date', start + 'T00:00:00');
    if (end)   params.set('end_date',   end   + 'T23:59:59');
    alertsData = await apiFetch('/alerts?' + params);
    renderAlertsPage();
  } catch (e) {
    showToast('Failed to load alerts: ' + e.message, 'error');
  }
}

function renderAlertsPage() {
  const el = document.getElementById('alerts-list');
  if (!el) return;
  const counts = { High: 0, Medium: 0, Low: 0 };
  alertsData.forEach(a => { if (counts[a.severity] !== undefined) counts[a.severity]++; });
  document.getElementById('alert-count-high').textContent   = counts.High;
  document.getElementById('alert-count-medium').textContent = counts.Medium;
  document.getElementById('alert-count-low').textContent    = counts.Low;
  document.getElementById('alert-count-total').textContent  = alertsData.length;

  el.innerHTML = alertsData.length ? alertsData.map(a => `
    <div class="alert-item">
      <div class="alert-dot ${(a.severity||'').toLowerCase()}"></div>
      <div class="alert-content">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <div class="alert-title">${a.alert_type}</div>
          ${severityBadge(a.severity)}
          ${a.acknowledged ? '<span style="font-size:11px;color:var(--green)">✓ Acknowledged</span>' : ''}
        </div>
        <div class="alert-desc">${a.explanation || ''}</div>
        <div class="alert-desc" style="margin-top:4px;color:var(--blue)">
          <strong>Action:</strong> ${a.action || ''}
        </div>
        <div class="alert-meta">
          <span>${fmtDate(a.timestamp)}</span>
          ${a.measured_value != null ? `<span>Measured: <strong>${fmt(a.measured_value,2)}</strong></span>` : ''}
          ${a.expected_value != null ? `<span>Expected: <strong>${fmt(a.expected_value,2)}</strong></span>` : ''}
          ${a.deviation_pct  != null ? `<span>Deviation: <strong>${fmt(a.deviation_pct,1)}%</strong></span>` : ''}
        </div>
      </div>
      ${!a.acknowledged ? `<button class="btn btn-sm btn-success" onclick="acknowledgeAlert(${a.id})">ACK</button>` : ''}
    </div>
  `).join('') : '<p style="color:var(--text-muted);font-size:13px;padding:16px">No alerts matching filters.</p>';

  // Threshold settings display
  apiFetch('/settings').then(s => {
    const bl = s.voltage_baseline?.value || '230';
    const th = s.voltage_threshold?.value || '4';
    document.getElementById('cfg-baseline').textContent  = bl + ' V';
    document.getElementById('cfg-threshold').textContent = th + '%';
  }).catch(() => {});
}

async function acknowledgeAlert(id) {
  try {
    await apiFetch(`/alerts/${id}/acknowledge`, { method: 'POST' });
    showToast('Alert acknowledged', 'success');
    loadAlerts();
  } catch (e) { showToast(e.message, 'error'); }
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('btn-filter-alerts')?.addEventListener('click', loadAlerts);
  document.getElementById('btn-clear-filters')?.addEventListener('click', () => {
    document.getElementById('filter-severity').value = '';
    document.getElementById('filter-start').value    = '';
    document.getElementById('filter-end').value      = '';
    loadAlerts();
  });
});

// ════════════════════════════════════════════════════════════════
//  BILL CALCULATOR
// ════════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('btn-calculate')?.addEventListener('click', calculateBill);
  // Pre-fill from settings
  apiFetch('/settings').then(s => {
    const rateEl = document.getElementById('calc-rate');
    if (rateEl && s.electricity_rate) rateEl.value = s.electricity_rate.value;
  }).catch(() => {});
});

function calculateBill() {
  const kwh       = parseFloat(document.getElementById('calc-kwh').value);
  const rate      = parseFloat(document.getElementById('calc-rate').value);
  const addl      = parseFloat(document.getElementById('calc-addl').value) || 0;
  const reduction = parseFloat(document.getElementById('calc-reduction').value) || 0;

  let valid = true;
  const clearErr = id => { const e = document.getElementById(id + '-err'); if(e) e.textContent=''; document.getElementById(id)?.classList.remove('error'); };
  const setErr   = (id, msg) => { valid=false; const e=document.getElementById(id+'-err');if(e)e.textContent=msg;document.getElementById(id)?.classList.add('error'); };

  clearErr('calc-kwh'); clearErr('calc-rate'); clearErr('calc-reduction');

  if (isNaN(kwh)  || kwh  <= 0)    setErr('calc-kwh',  'Enter a valid consumption > 0');
  if (isNaN(rate) || rate <= 0)    setErr('calc-rate', 'Enter a valid rate > 0');
  if (reduction < 0 || reduction >= 100) setErr('calc-reduction', 'Enter 0–99');

  if (!valid) return;

  const energyCost  = kwh * rate;
  const totalBill   = energyCost + addl;
  const reducedKwh  = kwh * (1 - reduction / 100);
  const reducedCost = reducedKwh * rate + addl;
  const saved       = totalBill - reducedCost;

  document.getElementById('calc-result').style.display = 'block';
  document.getElementById('calc-total').textContent = '₹ ' + fmt(totalBill, 2);
  document.getElementById('calc-energy-cost').textContent = '₹ ' + fmt(energyCost, 2);
  document.getElementById('calc-addl-display').textContent = '₹ ' + fmt(addl, 2);
  document.getElementById('calc-total-row').textContent    = '₹ ' + fmt(totalBill, 2);

  if (reduction > 0) {
    document.getElementById('calc-savings-section').style.display = 'block';
    document.getElementById('calc-reduced-kwh').textContent    = fmt(reducedKwh, 3) + ' kWh';
    document.getElementById('calc-reduced-bill').textContent   = '₹ ' + fmt(reducedCost, 2);
    document.getElementById('calc-saved-amount').textContent   = '₹ ' + fmt(saved, 2);

    // Update bar chart comparison
    renderBarChart('chart-bill-compare', {
      labels: ['Current', 'After Reduction'],
      datasets: [{
        label: 'Bill (₹)',
        data: [totalBill, reducedCost],
        backgroundColor: ['rgba(239,68,68,0.6)', 'rgba(16,185,129,0.6)'],
        borderColor:     ['#ef4444', '#10b981'],
        borderWidth: 2, borderRadius: 6,
      }]
    });
    document.getElementById('calc-chart-section').style.display = 'block';
  } else {
    document.getElementById('calc-savings-section').style.display = 'none';
    document.getElementById('calc-chart-section').style.display   = 'none';
  }
}

// ════════════════════════════════════════════════════════════════
//  RECOMMENDATIONS
// ════════════════════════════════════════════════════════════════
function getRecommendationData() {
  return [
    {
      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>',
      iconBg: 'rgba(245,158,11,0.12)', title: 'Switch Off Unused Lights',
      desc: 'Turn off lights in unoccupied rooms. A single 60W bulb left on for 8 hours wastes 0.48 kWh per day.',
      saving: 'Estimated saving: ₹3–10/day (varies by tariff and number of lights)',
    },
    {
      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>',
      iconBg: 'rgba(59,130,246,0.12)', title: 'Turn Off Standby Electronics',
      desc: 'TVs, computers, and chargers in standby can consume 5–15% of total household electricity. Use power strips.',
      saving: 'Estimated saving: ₹20–60/month',
    },
    {
      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
      iconBg: 'rgba(16,185,129,0.12)', title: 'Optimise Air Conditioning',
      desc: 'Set AC to 24–26°C instead of 18–20°C. Each degree reduction increases power consumption by ~6%.',
      saving: 'Estimated saving: ₹100–400/month during summer',
    },
    {
      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>',
      iconBg: 'rgba(139,92,246,0.12)', title: 'Investigate High Power Readings',
      desc: 'When consumption exceeds normal levels, identify the cause. Faulty appliances can consume 2–5× normal power.',
      saving: 'Fault detection can prevent significant waste',
    },
    {
      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
      iconBg: 'rgba(0,212,255,0.12)', title: 'Schedule Heavy Loads Off-Peak',
      desc: 'Run washing machines, dishwashers, and water heaters during off-peak hours (late night or early morning).',
      saving: 'Reduces peak demand; some tariffs offer off-peak discounts',
    },
    {
      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
      iconBg: 'rgba(16,185,129,0.12)', title: 'Track and Compare Usage',
      desc: 'Use this dashboard to compare weekly and monthly consumption. Awareness of usage patterns leads to behaviour changes.',
      saving: 'Studies show monitoring alone reduces usage by 5–15%',
    },
  ];
}

async function loadRecommendations() {
  const el = document.getElementById('recs-list');
  if (!el) return;
  const recs = getRecommendationData();
  el.innerHTML = recs.map(r => `
    <div class="rec-item">
      <div class="rec-icon" style="background:${r.iconBg}">${r.icon}</div>
      <div style="flex:1">
        <div class="rec-title">${r.title}</div>
        <div class="rec-desc">${r.desc}</div>
        ${r.saving ? `<div class="rec-saving">💡 ${r.saving}</div>` : ''}
      </div>
    </div>
  `).join('');
}

// ════════════════════════════════════════════════════════════════
//  READINGS
// ════════════════════════════════════════════════════════════════
let readingsState = { page: 1, per_page: 20, sort_by: 'timestamp', sort_dir: 'desc', total: 0 };

async function loadReadings() {
  const search = document.getElementById('readings-search')?.value || '';
  const start  = document.getElementById('readings-start')?.value  || '';
  const end    = document.getElementById('readings-end')?.value    || '';
  const source = document.getElementById('readings-source')?.value || '';
  const params = new URLSearchParams({
    page: readingsState.page, per_page: readingsState.per_page,
    sort_by: readingsState.sort_by, sort_dir: readingsState.sort_dir,
    search, source,
  });
  if (start) params.set('start_date', start + 'T00:00:00');
  if (end)   params.set('end_date',   end   + 'T23:59:59');

  try {
    const data = await apiFetch('/readings?' + params);
    readingsState.total = data.total;
    renderReadingsTable(data.readings);
    renderPagination(data);
  } catch (e) {
    showToast('Failed to load readings: ' + e.message, 'error');
  }
}

function renderReadingsTable(readings) {
  const tbody = document.getElementById('readings-tbody');
  if (!tbody) return;
  tbody.innerHTML = readings.length ? readings.map(r => `
    <tr>
      <td class="mono" style="font-size:11px;white-space:nowrap">${fmtDate(r.timestamp)}</td>
      <td class="mono">${fmt(r.voltage, 1)}</td>
      <td class="mono">${fmt(r.current, 3)}</td>
      <td class="mono">${fmt(r.power,   1)}</td>
      <td class="mono">${fmt(r.energy_kwh, 4)}</td>
      <td>${r.device_id || '—'}</td>
      <td>${sourceBadge(r.source || 'Manual')}</td>
      <td>${statusBadge(r.status || 'Normal')}</td>
    </tr>
  `).join('') : '<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:24px">No readings found.</td></tr>';
}

function renderPagination(data) {
  const el = document.getElementById('readings-pagination');
  if (!el) return;
  const { page, pages, total, per_page } = data;
  const start = (page - 1) * per_page + 1;
  const end   = Math.min(page * per_page, total);
  let html = `<span class="page-info">${start}–${end} of ${total}</span>`;
  html += `<button class="page-btn" onclick="changePage(${page-1})" ${page<=1?'disabled':''}>‹</button>`;
  const first = Math.max(1, page - 2), last = Math.min(pages, page + 2);
  for (let p = first; p <= last; p++) {
    html += `<button class="page-btn ${p===page?'active':''}" onclick="changePage(${p})">${p}</button>`;
  }
  html += `<button class="page-btn" onclick="changePage(${page+1})" ${page>=pages?'disabled':''}>›</button>`;
  el.innerHTML = html;
}

function changePage(p) { readingsState.page = p; loadReadings(); }

// Sort
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('#readings-table th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      if (readingsState.sort_by === th.dataset.sort) {
        readingsState.sort_dir = readingsState.sort_dir === 'desc' ? 'asc' : 'desc';
      } else {
        readingsState.sort_by  = th.dataset.sort;
        readingsState.sort_dir = 'desc';
      }
      readingsState.page = 1;
      loadReadings();
    });
  });

  // Search / filter
  document.getElementById('btn-search-readings')?.addEventListener('click', () => {
    readingsState.page = 1; loadReadings();
  });
  document.getElementById('readings-search')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') { readingsState.page = 1; loadReadings(); }
  });

  // Add reading form
  document.getElementById('btn-add-reading')?.addEventListener('click', addReading);

  // CSV Export
  document.getElementById('btn-export-csv')?.addEventListener('click', () => {
    window.location.href = '/api/readings/export';
    showToast('Downloading CSV…', 'info');
  });

  // Reset data
  document.getElementById('btn-reset-data')?.addEventListener('click', async () => {
    if (!confirm('This will delete all current readings and restore the original 30-day sample dataset. Continue?')) return;
    try {
      await apiFetch('/readings/reset', { method: 'POST' });
      showToast('Sample data restored!', 'success');
      loadReadings();
      loadDashboard();
    } catch (e) { showToast(e.message, 'error'); }
  });

  // CSV import
  document.getElementById('btn-import-csv')?.addEventListener('click', () => {
    document.getElementById('csv-file-input').click();
  });
  document.getElementById('csv-file-input')?.addEventListener('change', importCSV);
});

async function addReading() {
  const get = id => document.getElementById(id)?.value.trim();
  const setErr = (id, msg) => { const e = document.getElementById(id+'-err'); if(e) e.textContent=msg; document.getElementById(id)?.classList.add('error'); };
  const clrErr = id => { const e = document.getElementById(id+'-err'); if(e) e.textContent=''; document.getElementById(id)?.classList.remove('error'); };

  ['add-voltage','add-current','add-power','add-energy','add-device','add-source'].forEach(clrErr);
  let valid = true;
  const voltage = parseFloat(get('add-voltage'));
  const current = parseFloat(get('add-current'));
  if (isNaN(voltage)) { setErr('add-voltage','Required'); valid=false; }
  if (isNaN(current)) { setErr('add-current','Required'); valid=false; }
  if (!valid) return;

  const body = {
    voltage, current,
    power:      get('add-power')  ? parseFloat(get('add-power'))  : undefined,
    energy_kwh: get('add-energy') ? parseFloat(get('add-energy')) : undefined,
    device_id:  get('add-device') || 'ESP32-01',
    source:     get('add-source') || 'Manual',
    timestamp:  new Date().toISOString().slice(0,19),
  };
  try {
    await apiFetch('/readings', { method:'POST', body: JSON.stringify(body) });
    showToast('Reading added successfully!', 'success');
    // Clear form
    ['add-voltage','add-current','add-power','add-energy'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
    readingsState.page = 1;
    loadReadings();
    if (currentPage === 'dashboard') loadDashboard();
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
}

async function importCSV(event) {
  const file = event.target.files[0];
  if (!file) return;
  const text = await file.text();
  const lines = text.split('\n').filter(l => l.trim());
  const header = lines[0].split(',').map(h => h.trim().toLowerCase());
  const idxOf  = col => header.indexOf(col);

  let imported = 0, skipped = 0;
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(',');
    const row  = {};
    header.forEach((h, j) => row[h] = cols[j]?.trim());
    try {
      await apiFetch('/readings', {
        method: 'POST',
        body: JSON.stringify({
          timestamp:  row.timestamp || new Date().toISOString().slice(0,19),
          voltage:    parseFloat(row.voltage),
          current:    parseFloat(row.current),
          power:      parseFloat(row.power)      || undefined,
          energy_kwh: parseFloat(row.energy_kwh) || undefined,
          device_id:  row.device_id || 'Imported',
          source:     row.source    || 'Manual',
        })
      });
      imported++;
    } catch (_) { skipped++; }
  }
  showToast(`Imported ${imported} readings (${skipped} skipped/duplicate)`, imported > 0 ? 'success' : 'warning');
  event.target.value = '';
  loadReadings();
}

// ════════════════════════════════════════════════════════════════
//  SETTINGS
// ════════════════════════════════════════════════════════════════
async function loadSettings() {
  try {
    const [settings, health, tsStatus] = await Promise.all([
      apiFetch('/settings'),
      apiFetch('/health'),
      apiFetch('/thingspeak/status'),
    ]);

    // Fill form fields
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
    set('cfg-rate',      settings.electricity_rate?.value || '8');
    set('cfg-baseline',  settings.voltage_baseline?.value || '230');
    set('cfg-threshold', settings.voltage_threshold?.value || '4');
    set('cfg-consec',    settings.consec_threshold?.value || '3');
    set('cfg-ts-interval',settings.thingspeak_interval?.value || '60');
    set('cfg-field-v',   settings.field_voltage?.value || 'field1');
    set('cfg-field-a',   settings.field_current?.value || 'field2');
    set('cfg-field-w',   settings.field_power?.value   || 'field3');
    set('cfg-field-e',   settings.field_energy?.value  || 'field4');

    // Status display
    document.getElementById('dev-status').textContent     = 'Online';
    document.getElementById('dev-readings').textContent   = health.readings_count + ' readings';
    document.getElementById('dev-ts-config').textContent  = health.thingspeak_configured ? 'Configured' : 'Not Configured';
    document.getElementById('dev-ts-connect').textContent = tsStatus.connected ? 'Connected' : 'Disconnected';
    document.getElementById('dev-ts-reason').textContent  = tsStatus.reason || '';
    document.getElementById('dev-demo').textContent       = !health.thingspeak_configured ? 'Active' : 'Inactive';

    document.getElementById('dev-ts-connect').style.color = tsStatus.connected ? 'var(--green)' : 'var(--yellow)';
  } catch (e) {
    showToast('Failed to load settings: ' + e.message, 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('btn-save-settings')?.addEventListener('click', saveSettings);
  document.getElementById('btn-sync-ts')?.addEventListener('click', syncThingSpeak);
});

async function saveSettings() {
  const get = id => document.getElementById(id)?.value;
  const body = {
    electricity_rate:   get('cfg-rate'),
    voltage_baseline:   get('cfg-baseline'),
    voltage_threshold:  get('cfg-threshold'),
    consec_threshold:   get('cfg-consec'),
    thingspeak_interval:get('cfg-ts-interval'),
    field_voltage:      get('cfg-field-v'),
    field_current:      get('cfg-field-a'),
    field_power:        get('cfg-field-w'),
    field_energy:       get('cfg-field-e'),
  };
  try {
    const res = await apiFetch('/settings', { method: 'PUT', body: JSON.stringify(body) });
    showToast('Settings saved: ' + res.updated.join(', '), 'success');
  } catch (e) { showToast('Save failed: ' + e.message, 'error'); }
}

async function syncThingSpeak() {
  showToast('Syncing ThingSpeak data…', 'info');
  try {
    const res = await apiFetch('/thingspeak/sync', { method: 'POST' });
    if (res.status === 'disconnected') showToast('ThingSpeak not configured (demo mode)', 'warning');
    else showToast(`Synced: ${res.inserted} new readings imported`, 'success');
  } catch (e) { showToast('Sync failed: ' + e.message, 'error'); }
}
