// =============================================================
// Restock Predictor — Dashboard Application
// Reads from Supabase (anon key, read-only via RLS)
// =============================================================

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

// ---- Supabase credentials (anon key is safe to commit — RLS enforces read-only) ----
const SUPABASE_URL      = 'https://qjexokrgtpsqugmelsru.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFqZXhva3JndHBzcXVnbWVsc3J1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODkxNDgyMjAsImV4cCI6MjEwNDcyNDIyMH0.nPo0koFVsEgxv5G5xXAduULQjWXgc0WWgqh8t3v9YHU';

const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// ---- Constants ----
const REFRESH_INTERVAL_MS = 5 * 60 * 1000;   // 5 minutes

// ---- State ----
let currentFilter = 'all';
let predictionsData = [];
let historyData = [];

// ---- Boot ----
document.addEventListener('DOMContentLoaded', async () => {
  setupFilterTabs();
  await loadDashboard();
  setInterval(loadDashboard, REFRESH_INTERVAL_MS);
});

// =============================================================
// Data fetching
// =============================================================

/**
 * Load all dashboard data from Supabase and render.
 */
async function loadDashboard() {
  try {
    const [predictions, orders, items] = await Promise.all([
      fetchPredictions(),
      fetchOrderCount(),
      fetchItemCount(),
    ]);

    predictionsData = predictions;
    renderStats(predictions, orders, items);
    renderRestockGrid(predictions);
    renderHistoryTable(predictions);
    updateLastSync();
  } catch (err) {
    console.error('Dashboard load error:', err);
    showError('Could not load data. Check browser console for details.');
  }
}

/**
 * Fetch predictions joined with item names.
 * @returns {Promise<Array>} Prediction rows with item info.
 */
async function fetchPredictions() {
  const { data, error } = await supabase
    .from('predictions')
    .select(`
      *,
      items ( id, name, display_name, unit, category )
    `)
    .order('predicted_restock_date', { ascending: true });

  if (error) throw error;
  return data || [];
}

/**
 * Fetch total order count.
 * @returns {Promise<number>}
 */
async function fetchOrderCount() {
  const { count, error } = await supabase
    .from('orders')
    .select('*', { count: 'exact', head: true });

  if (error) throw error;
  return count || 0;
}

/**
 * Fetch total unique item count.
 * @returns {Promise<number>}
 */
async function fetchItemCount() {
  const { count, error } = await supabase
    .from('items')
    .select('*', { count: 'exact', head: true });

  if (error) throw error;
  return count || 0;
}

// =============================================================
// Rendering — Stats Bar
// =============================================================

/**
 * Render the summary stat cards.
 * @param {Array} predictions
 * @param {number} orderCount
 * @param {number} itemCount
 */
function renderStats(predictions, orderCount, itemCount) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const weekFromNow = new Date(today);
  weekFromNow.setDate(weekFromNow.getDate() + 7);

  let dueSoon = 0;
  let overdue = 0;

  for (const p of predictions) {
    const restockDate = new Date(p.predicted_restock_date);
    if (restockDate < today) {
      overdue++;
    } else if (restockDate <= weekFromNow) {
      dueSoon++;
    }
  }

  setText('stat-items', itemCount);
  setText('stat-orders', orderCount);
  setText('stat-due-soon', dueSoon);
  setText('stat-overdue', overdue);
}

// =============================================================
// Rendering — Restock Timeline
// =============================================================

/**
 * Render the restock card grid with current filter applied.
 * @param {Array} predictions
 */
function renderRestockGrid(predictions) {
  const grid = document.getElementById('restock-grid');
  const countBadge = document.getElementById('restock-count');

  if (!predictions.length) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-state__icon">📭</div>
        <p class="empty-state__text">
          No predictions yet. Run the sync pipeline to fetch your order emails
          and generate restock forecasts.
        </p>
      </div>`;
    countBadge.textContent = '0 items';
    return;
  }

  const filtered = filterPredictions(predictions, currentFilter);
  countBadge.textContent = `${filtered.length} item${filtered.length !== 1 ? 's' : ''}`;

  if (!filtered.length) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-state__icon">✅</div>
        <p class="empty-state__text">No items match this filter.</p>
      </div>`;
    return;
  }

  grid.innerHTML = filtered.map((p, i) => renderRestockCard(p, i)).join('');
}

/**
 * Render a single restock card.
 * @param {Object} prediction
 * @param {number} index — for staggered animation
 * @returns {string} HTML string
 */
function renderRestockCard(prediction, index) {
  const itemName = prediction.items?.display_name || prediction.items?.name || 'Unknown Item';
  const restockDate = new Date(prediction.predicted_restock_date);
  const lastOrdered = new Date(prediction.last_ordered);
  const daysUntil = getDaysUntil(restockDate);
  const urgency = getUrgency(daysUntil);
  const delay = Math.min(index * 0.06, 0.6);  // max 600ms stagger

  return `
    <article class="restock-card restock-card--${urgency}" style="animation-delay: ${delay}s"
             id="restock-${prediction.item_id}">
      <div class="restock-card__header">
        <h3 class="restock-card__name" title="${escapeHtml(itemName)}">${escapeHtml(itemName)}</h3>
        <span class="days-badge days-badge--${urgency}">
          ${formatDaysBadge(daysUntil)}
        </span>
      </div>
      <div class="restock-card__meta">
        <div class="restock-card__meta-row">
          <span class="restock-card__meta-label">Restock by</span>
          <span class="restock-card__meta-value">${formatDate(restockDate)}</span>
        </div>
        <div class="restock-card__meta-row">
          <span class="restock-card__meta-label">Last ordered</span>
          <span class="restock-card__meta-value">${formatDate(lastOrdered)}</span>
        </div>
        <div class="restock-card__meta-row">
          <span class="restock-card__meta-label">Avg interval</span>
          <span class="restock-card__meta-value">${prediction.ema_interval_days} days (EMA)</span>
        </div>
        <div class="restock-card__meta-row">
          <span class="restock-card__meta-label">Confidence</span>
          <span class="confidence-chip confidence-chip--${prediction.confidence}">
            ${confidenceIcon(prediction.confidence)} ${prediction.confidence}
          </span>
        </div>
      </div>
    </article>`;
}

// =============================================================
// Rendering — History Table
// =============================================================

/**
 * Render the consumption history table.
 * @param {Array} predictions
 */
function renderHistoryTable(predictions) {
  const tbody = document.getElementById('history-body');

  if (!predictions.length) {
    tbody.innerHTML = `
      <tr><td colspan="5">
        <div class="empty-state">
          <p class="empty-state__text">No purchase history yet.</p>
        </div>
      </td></tr>`;
    return;
  }

  // Find max times_purchased for bar chart scaling
  const maxPurchases = Math.max(...predictions.map(p => p.times_purchased || 1));

  // Sort by times_purchased descending for the table
  const sorted = [...predictions].sort((a, b) =>
    (b.times_purchased || 0) - (a.times_purchased || 0)
  );

  tbody.innerHTML = sorted.map(p => {
    const itemName = p.items?.display_name || p.items?.name || 'Unknown';
    const times = p.times_purchased || 0;
    const avgDays = p.avg_interval_days || '—';
    const emaDays = p.ema_interval_days || '—';
    const lastDate = p.last_ordered ? formatDate(new Date(p.last_ordered)) : '—';
    const barWidth = maxPurchases > 0 ? Math.round((times / maxPurchases) * 100) : 0;

    return `
      <tr>
        <td title="${escapeHtml(itemName)}">${escapeHtml(truncate(itemName, 40))}</td>
        <td>${times}×</td>
        <td>${avgDays}d</td>
        <td>
          <div class="freq-bar-wrap">
            <div class="freq-bar" style="width: ${barWidth}%"></div>
            <span class="freq-bar-label">every ${emaDays}d</span>
          </div>
        </td>
        <td>${lastDate}</td>
      </tr>`;
  }).join('');
}

// =============================================================
// Filters
// =============================================================

/**
 * Set up click handlers on filter tabs.
 */
function setupFilterTabs() {
  const tabs = document.getElementById('filter-tabs');
  tabs.addEventListener('click', (e) => {
    const tab = e.target.closest('.filter-tab');
    if (!tab) return;

    // Update active state
    tabs.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('filter-tab--active'));
    tab.classList.add('filter-tab--active');

    currentFilter = tab.dataset.filter;
    renderRestockGrid(predictionsData);
  });
}

/**
 * Filter predictions by urgency category.
 * @param {Array} predictions
 * @param {string} filter — 'all', 'urgent', 'soon', 'ok'
 * @returns {Array}
 */
function filterPredictions(predictions, filter) {
  if (filter === 'all') return predictions;

  return predictions.filter(p => {
    const days = getDaysUntil(new Date(p.predicted_restock_date));
    const urgency = getUrgency(days);
    if (filter === 'urgent') return urgency === 'urgent' || urgency === 'past';
    if (filter === 'soon')   return urgency === 'soon';
    if (filter === 'ok')     return urgency === 'ok';
    return true;
  });
}

// =============================================================
// Helpers
// =============================================================

/**
 * Calculate days from today until the target date.
 * @param {Date} targetDate
 * @returns {number} Days until target (negative = past due)
 */
function getDaysUntil(targetDate) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(targetDate);
  target.setHours(0, 0, 0, 0);
  return Math.round((target - today) / (1000 * 60 * 60 * 24));
}

/**
 * Map days-until to urgency level.
 * @param {number} days
 * @returns {string} 'past' | 'urgent' | 'soon' | 'ok'
 */
function getUrgency(days) {
  if (days < 0)  return 'past';
  if (days <= 3) return 'urgent';
  if (days <= 7) return 'soon';
  return 'ok';
}

/**
 * Format a days-until number for the badge.
 * @param {number} days
 * @returns {string}
 */
function formatDaysBadge(days) {
  if (days < 0)  return `${Math.abs(days)}d overdue`;
  if (days === 0) return 'Today!';
  if (days === 1) return 'Tomorrow';
  return `${days}d`;
}

/**
 * Format a Date as a readable string.
 * @param {Date} date
 * @returns {string}
 */
function formatDate(date) {
  return date.toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

/**
 * Return an icon for a confidence level.
 * @param {string} level
 * @returns {string}
 */
function confidenceIcon(level) {
  const icons = { high: '●', medium: '◐', low: '○' };
  return icons[level] || '○';
}

/**
 * Truncate a string with ellipsis.
 * @param {string} str
 * @param {number} max
 * @returns {string}
 */
function truncate(str, max) {
  return str.length > max ? str.slice(0, max - 1) + '…' : str;
}

/**
 * Escape HTML special characters.
 * @param {string} str
 * @returns {string}
 */
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/**
 * Set text content of an element by ID.
 * @param {string} id
 * @param {string|number} text
 */
function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

/**
 * Show an error banner on the page.
 * @param {string} message
 */
function showError(message) {
  const grid = document.getElementById('restock-grid');
  grid.innerHTML = `
    <div class="error-state">
      <p>⚠️ ${escapeHtml(message)}</p>
    </div>`;
}

/**
 * Update the "last sync" timestamp in the footer.
 */
function updateLastSync() {
  const el = document.getElementById('last-sync');
  if (el) {
    el.textContent = new Date().toLocaleString('en-IN', {
      day: 'numeric', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  }
}
