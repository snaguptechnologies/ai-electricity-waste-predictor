/**
 * AI Electricity Waste Predictor – app.js
 * Core utilities: navigation, toast, API helpers, sidebar
 */

const API = '/api';

// ── Navigation ──────────────────────────────────────────────────────────────
let currentPage = 'dashboard';

function navigate(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const pageEl = document.getElementById(`page-${page}`);
  if (pageEl) pageEl.classList.add('active');
  const navEl = document.querySelector(`.nav-item[data-page="${page}"]`);
  if (navEl) navEl.classList.add('active');
  currentPage = page;
  // Close mobile sidebar
  closeSidebar();
  // Load page data
  loadPage(page);
}

function loadPage(page) {
  switch (page) {
    case 'dashboard':    loadDashboard(); break;
    case 'predictions':  loadPredictions(); break;
    case 'alerts':       loadAlerts(); break;
    case 'calculator':   /* static UI, no data fetch */ break;
    case 'recommendations': loadRecommendations(); break;
    case 'readings':     loadReadings(); break;
    case 'settings':     loadSettings(); break;
  }
}

// ── Sidebar ──────────────────────────────────────────────────────────────────
function openSidebar() {
  document.querySelector('.sidebar').classList.add('open');
  document.querySelector('.sidebar-overlay').classList.add('visible');
}
function closeSidebar() {
  document.querySelector('.sidebar').classList.remove('open');
  document.querySelector('.sidebar-overlay').classList.remove('visible');
}

// ── Toast ────────────────────────────────────────────────────────────────────
function showToast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  const icons = {
    success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
    error:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    info:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
    warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
  };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `${icons[type] || icons.info}<span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease forwards';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ── API helper ───────────────────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  try {
    const res = await fetch(API + path, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    return await res.json();
  } catch (e) {
    console.error(`[API] ${path}`, e);
    throw e;
  }
}

// ── Formatting helpers ───────────────────────────────────────────────────────
function fmt(val, dec = 2) {
  if (val == null || isNaN(val)) return '—';
  return Number(val).toFixed(dec);
}
function fmtDate(ts) {
  if (!ts) return '—';
  const d = new Date(ts.replace('T', ' ') + (ts.includes('Z') ? '' : ' UTC'));
  return d.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true });
}
function fmtShortDate(ts) {
  if (!ts) return '—';
  const d = new Date(ts.replace('T', ' ') + ' UTC');
  return d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
}
function severityBadge(sev) {
  const s = (sev || '').toLowerCase();
  return `<span class="badge badge-${s}">${sev}</span>`;
}
function sourceBadge(src) {
  const s = (src || '').toLowerCase().replace(/\s+/g, '');
  return `<span class="badge badge-${s}">${src}</span>`;
}
function statusBadge(st) {
  const s = (st || '').toLowerCase();
  return `<span class="badge badge-${s}">${st}</span>`;
}

// ── Chart default theme ──────────────────────────────────────────────────────
const CHART_DEFAULTS = {
  borderWidth: 2,
  pointRadius: 0,
  tension: 0.4,
  fill: true,
};
function chartGradient(ctx, color1, color2 = 'transparent') {
  const g = ctx.createLinearGradient(0, 0, 0, 220);
  g.addColorStop(0, color1);
  g.addColorStop(1, color2);
  return g;
}
Chart.defaults.color = '#64748b';
Chart.defaults.borderColor = '#1e2d45';
Chart.defaults.font.family = 'Inter';
Chart.defaults.font.size = 11;

// ── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Nav clicks
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => navigate(item.dataset.page));
  });
  // Hamburger
  document.querySelector('.hamburger')?.addEventListener('click', openSidebar);
  document.querySelector('.sidebar-overlay')?.addEventListener('click', closeSidebar);

  // Load initial page
  navigate('dashboard');

  // Refresh button in topbar
  document.getElementById('btn-refresh')?.addEventListener('click', () => {
    loadPage(currentPage);
    showToast('Data refreshed', 'success');
  });
});
