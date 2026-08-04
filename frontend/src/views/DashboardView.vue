<template>
  <div class="page dashboard-page">
    <div class="dashboard-shell">
      <aside
        :class="['dashboard-sidebar', { expanded: isSidebarExpanded, pinned: sidebarPinned }]"
        @mouseenter="handleSidebarMouseEnter"
        @mouseleave="handleSidebarMouseLeave"
      >
        <div class="dashboard-sidebar-top">
          <button
            class="dashboard-sidebar-handle"
            type="button"
            @click.stop="toggleSidebarHandle"
            :aria-expanded="isSidebarExpanded"
            :title="sidebarPinned ? 'Sidebar pinned open' : (isSidebarExpanded ? 'Collapse sidebar' : 'Expand sidebar')"
          >
            <span class="sidebar-icon">☰</span>
            <span v-if="isSidebarExpanded" class="sidebar-handle-label">Dashboard</span>
          </button>

          <button
            v-if="isSidebarExpanded"
            class="dashboard-sidebar-pin"
            type="button"
            @click.stop="toggleSidebarPinned"
            :aria-pressed="sidebarPinned"
            :title="sidebarPinned ? 'Unpin sidebar' : 'Pin sidebar open'"
          >
            <span class="dashboard-sidebar-pin-icon">{{ sidebarPinned ? '📌' : '📍' }}</span>
            <span class="dashboard-sidebar-pin-label">{{ sidebarPinned ? 'Pinned' : 'Pin' }}</span>
          </button>
        </div>

        <div v-if="!isSidebarExpanded" class="dashboard-sidebar-rail">
          <div class="dashboard-rail-badge active">T</div>
          <div class="dashboard-rail-badge">W</div>
          <div class="dashboard-rail-badge">F</div>
          <div class="dashboard-rail-badge">D</div>
        </div>

        <div v-else class="dashboard-sidebar-content">
          <div class="dashboard-sidebar-section">
            <div class="dashboard-sidebar-title">Tabs</div>
            <div class="dashboard-sidebar-list">
              <button
                v-for="tab in tabs"
                :key="tab.id"
                :class="['dashboard-sidebar-tab', { active: String(tab.id) === String(selectedTabId) }]"
                @click="selectTab(tab.id)"
              >
                <span class="dashboard-sidebar-tab-dot"></span>
                <span class="dashboard-sidebar-tab-text">{{ tab.name }}</span>
              </button>
            </div>
            <div class="dashboard-sidebar-action-grid">
              <button class="secondary dashboard-sidebar-action" @click="createTab">New Tab</button>
              <button class="secondary dashboard-sidebar-action" @click="renameTab" :disabled="!activeTab">Rename</button>
              <button class="secondary dashboard-sidebar-action danger" @click="deleteTab" :disabled="tabs.length <= 1">Delete</button>
            </div>
          </div>

          <div class="dashboard-sidebar-section">
            <div class="dashboard-sidebar-title">Widgets</div>
            <div class="widget-toggle-grid widget-toggle-grid-sidebar">
              <label v-for="widget in widgetOptions" :key="widget.id" class="widget-toggle-item sidebar-widget-item">
                <input type="checkbox" :checked="showWidget(widget.id)" @change="toggleWidget(widget.id)" />
                <span>{{ widget.label }}</span>
              </label>
            </div>
          </div>

          <div class="dashboard-sidebar-section">
            <div class="dashboard-sidebar-title">Quick Range</div>
            <div class="dashboard-sidebar-chip-grid">
              <button
                v-for="item in quickRanges"
                :key="item.key"
                :class="['tv-range-chip sidebar-range-chip', { active: activeQuickRange === item.key }]"
                @click="applyQuickRange(item.key)"
              >
                {{ item.label }}
              </button>
            </div>
          </div>

          <div class="dashboard-sidebar-section">
            <div class="dashboard-sidebar-title">Filters</div>
            <div v-if="filterOptionsLoaded" class="dashboard-sidebar-form">
              <label class="dashboard-sidebar-field">
                <span>Account</span>
                <div class="dashboard-account-boundary">{{ activeAccountCode }}</div>
              </label>
              <label class="dashboard-sidebar-field">
                <span>Symbol</span>
                <select v-model="filters.symbol">
                  <option value="">All Symbols</option>
                  <option v-for="item in filterOptions.symbols" :key="item" :value="item">{{ item }}</option>
                </select>
              </label>
              <label class="dashboard-sidebar-field">
                <span>Strategy</span>
                <select v-model="filters.strategy">
                  <option value="">All Strategies</option>
                  <option v-for="item in filterOptions.strategies" :key="item" :value="item">{{ item }}</option>
                </select>
              </label>
              <label class="dashboard-sidebar-field">
                <span>Asset Class</span>
                <select v-model="filters.asset_class">
                  <option value="">All Asset Classes</option>
                  <option v-for="item in filterOptions.asset_classes" :key="item" :value="item">{{ item }}</option>
                </select>
              </label>
              <label class="dashboard-sidebar-field">
                <span>Date From</span>
                <input v-model="filters.date_from" type="date" @click="openDatePicker" @focus="openDatePicker" />
              </label>
              <label class="dashboard-sidebar-field">
                <span>Date To</span>
                <input v-model="filters.date_to" type="date" @click="openDatePicker" @focus="openDatePicker" />
              </label>
            </div>
            <div v-else class="dashboard-sidebar-loading">
              {{ filterOptionsLoading ? 'Loading filters...' : 'Open sidebar to load filters' }}
            </div>
            <div class="dashboard-sidebar-action-grid single-row">
              <button class="dashboard-sidebar-primary" @click="applyFilters">Apply</button>
              <button class="secondary dashboard-sidebar-action" @click="resetFilters">Reset</button>
            </div>
          </div>
        </div>
      </aside>

      <div class="dashboard-main">
        <div class="tv-header card dashboard-main-header">
          <div>
            <div class="tv-kicker">Custom Dashboards</div>
            <h1 class="tv-page-title dashboard-main-title">{{ activeTab?.name || 'Dashboard' }}</h1>
            <p class="tv-page-subtitle">用更紧凑的工作台方式查看区间统计、图表和交易明细。</p>
          </div>
          <div class="dashboard-main-meta">
            <div class="tv-summary-chip">{{ selectedAccountLabel }}</div>
            <div class="tv-summary-chip">{{ dateSummaryLabel }}</div>
          </div>
        </div>

        <div class="dashboard-workbench dashboard-workbench-embedded">
          <div class="tv-stats-grid tv-stats-grid-compact">
            <StatCard v-if="showWidget('overviewCards')" label="Trade Groups" :value="stats.trade_count" compact />
            <StatCard v-if="showWidget('overviewCards')" label="Open Positions" :value="stats.open_positions" compact />
            <StatCard v-if="showWidget('overviewCards')" label="Total PnL" :value="stats.total_realized_pnl" compact />
            <StatCard v-if="showWidget('overviewCards')" label="Per Trade Avg PnL" :value="stats.avg_pnl_per_trade" compact />
            <StatCard v-if="showWidget('performanceCards')" label="Win Rate" :value="formatPercent(stats.win_rate)" compact />
            <StatCard v-if="showWidget('performanceCards')" label="Profit Factor" :value="stats.profit_factor || '-'" compact />
            <StatCard v-if="showWidget('performanceCards')" label="Expectancy" :value="stats.expectancy" compact />
            <StatCard v-if="showWidget('performanceCards')" label="Commission" :value="stats.total_commission" compact />
          </div>

          <div class="tv-dashboard-chart-grid tv-dashboard-chart-grid-triple sortable-chart-grid">
            <div
              v-for="panel in orderedPanels"
              :key="panel.id"
              class="sortable-panel"
              draggable="true"
              @dragstart="onPanelDragStart(panel.id)"
              @dragover.prevent
              @drop="onPanelDrop(panel.id)"
            >
              <TradesVizChart
                v-if="panel.id === 'dailyPnl'"
                title="Daily Realized PnL"
                subtitle="Realized PnL over the selected range"
                :categories="pnlCategories"
                :series="pnlSeries"
                default-type="bar"
                :height="182"
              />
              <TradesVizChart
                v-else-if="panel.id === 'winsLosses'"
                title="Daily Wins / Losses"
                subtitle="Winning vs losing days"
                :categories="winsLossCategories"
                :series="winsLossSeries"
                default-type="bar"
                :height="182"
              />
              <TradesVizChart
                v-else-if="panel.id === 'cumulativePnl'"
                title="Cumulative PnL"
                subtitle="Track cumulative performance over time"
                :categories="cumulativeCategories"
                :series="cumulativeSeries"
                default-type="line"
                :height="182"
              />
              <TradesVizChart
                v-else-if="panel.id === 'symbolPnl'"
                title="PnL by Symbol"
                subtitle="Compare symbol performance"
                :categories="symbolCategories"
                :series="symbolSeries"
                default-type="bar"
                :height="182"
              />
              <div v-else class="card tv-mini-analytics-card">
                <div class="tv-chart-head tv-chart-head-flat">
                  <div>
                    <div class="tv-chart-title">Closed Trade Analytics</div>
                    <div class="tv-chart-subtitle">Compact snapshot</div>
                  </div>
                </div>
                <div class="tv-mini-analytics-grid">
                  <StatCard label="Wins" :value="stats.winning_trade_count" compact />
                  <StatCard label="Losses" :value="stats.losing_trade_count" compact />
                  <StatCard label="Avg Win" :value="stats.avg_win" compact />
                  <StatCard label="Avg Loss" :value="stats.avg_loss" compact />
                  <StatCard label="Largest Win" :value="stats.largest_win" compact />
                  <StatCard label="Largest Loss" :value="stats.largest_loss" compact />
                </div>
              </div>
            </div>
          </div>

          <div v-if="showWidget('processAnalytics')" class="card tv-tabbed-panel tv-tabbed-panel-compact">
            <div class="tv-panel-head">
              <div class="tv-chart-title">Process Analytics</div>
              <div class="tv-panel-meta">How you win / lose</div>
            </div>
            <div class="tv-dashboard-chart-grid tv-dashboard-chart-grid-triple">
              <TradesVizChart
                title="PnL by Setup"
                subtitle="Process edge by setup"
                :categories="setupCategories"
                :series="setupPnlSeries"
                default-type="bar"
                :height="182"
              />
              <TradesVizChart
                title="Win Rate by Setup"
                subtitle="Setup quality consistency"
                :categories="setupCategories"
                :series="setupWinRateSeries"
                default-type="bar"
                :height="182"
              />
              <TradesVizChart
                title="Avg R by Setup"
                subtitle="Risk-adjusted performance"
                :categories="setupCategories"
                :series="setupAvgRSeries"
                default-type="bar"
                :height="182"
              />
              <TradesVizChart
                title="PnL by Session"
                subtitle="Which session hurts or helps"
                :categories="sessionCategories"
                :series="sessionPnlSeries"
                default-type="bar"
                :height="182"
              />
              <TradesVizChart
                title="Overnight vs Intraday PnL"
                subtitle="Holding style contribution"
                :categories="overnightCategories"
                :series="overnightSeries"
                default-type="bar"
                :height="182"
              />
              <TradesVizChart
                title="First Trade vs Later Trades"
                subtitle="Intraday sequencing effect"
                :categories="firstLaterCategories"
                :series="firstLaterSeries"
                default-type="bar"
                :height="182"
              />
            </div>
            <div class="tv-mini-analytics-grid" style="margin-top: 12px;">
              <StatCard label="Rule Violations" :value="stats.charts?.rule_violations_count || 0" compact />
              <StatCard label="Early Exit Rate" :value="formatPercent(stats.charts?.early_exit_rate || 0)" compact />
              <StatCard label="Over-hold Rate" :value="formatPercent(stats.charts?.over_hold_rate || 0)" compact />
              <StatCard label="Top Mistake Tag" :value="topMistakeTag" compact />
              <StatCard label="2nd Mistake Tag" :value="secondMistakeTag" compact />
              <StatCard label="Repeated Symbol PnL" :value="repeatedSymbolPnl" compact />
            </div>
          </div>

          <div v-if="showWidget('detailTabs')" class="card tv-tabbed-panel tv-tabbed-panel-compact">
            <div class="tv-panel-head">
              <div class="tv-panel-tabs">
                <button :class="['tv-subtab', { active: detailTab==='latest' }]" @click="detailTab='latest'">Latest Trades</button>
                <button :class="['tv-subtab', { active: detailTab==='closed' }]" @click="detailTab='closed'">Closed Analytics</button>
              </div>
              <div class="tv-panel-meta">
                <span v-if="detailTab==='latest'">{{ latestCount }} trades</span>
                <span v-else>{{ closedCount }} closed trades</span>
              </div>
            </div>

            <div v-if="detailTab==='latest'">
              <div class="tv-table-wrap tv-table-wrap-compact">
                <TradeTable :rows="rows" />
              </div>
              <PaginationControls :count="latestCount" :current-page="latestPage" :page-size="detailPageSize" @change="loadRows" />
              <div class="tv-inline-actions"><router-link class="inline-link" to="/trades">View all trades</router-link></div>
            </div>

            <div v-else>
              <div class="tv-analytics-grid compact-grid">
                <StatCard label="Winning Trades" :value="stats.winning_trade_count" compact />
                <StatCard label="Losing Trades" :value="stats.losing_trade_count" compact />
                <StatCard label="Average Win" :value="stats.avg_win" compact />
                <StatCard label="Average Loss" :value="stats.avg_loss" compact />
                <StatCard label="Largest Win" :value="stats.largest_win" compact />
                <StatCard label="Largest Loss" :value="stats.largest_loss" compact />
                <StatCard label="Avg Hold Minutes" :value="stats.avg_hold_minutes" compact />
                <StatCard label="PnL Ratio" :value="stats.pnl_ratio || '-'" compact />
              </div>
              <div class="tv-table-wrap tv-table-wrap-compact">
                <TradeTable :rows="closedRows" />
              </div>
              <PaginationControls :count="closedCount" :current-page="closedPage" :page-size="detailPageSize" @change="loadClosedRows" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { responseCount, responseRows } from '../api/pagination'
import {
  fetchTradeDashboard,
  fetchTradeGroups,
  fetchTradeFilterOptions,
  fetchClosedTradeAnalytics,
} from '../api/trades'
import {
  fetchDashboardPreferences,
  fetchDashboardTabs,
  createDashboardTab,
  updateDashboardTab,
  deleteDashboardTab,
  saveDashboardPreferences,
} from '../api/common'
import StatCard from '../components/StatCard.vue'
import TradeTable from '../components/TradeTable.vue'
import TradesVizChart from '../components/TradesVizChart.vue'
import PaginationControls from '../components/PaginationControls.vue'
import { useAccounts } from '../state/accounts'

const DASHBOARD_SELECTED_KEY = 'trade-dashboard-selected-v100'
const DASHBOARD_WIDGET_SCHEMA_KEY = 'trade-dashboard-widget-schema-v2'
const DASHBOARD_STATE_KEY = 'trade-dashboard-state-v3'
const accountStorageKey = (baseKey) => `${baseKey}:${activeAccountCode.value || 'unselected'}`
const DEFAULT_FILTERS = {
  date_from: '',
  date_to: '',
  account: '',
  symbol: '',
  strategy: '',
  asset_class: '',
}
const quickRanges = [
  { key: 'all', label: 'All' },
  { key: '7d', label: '7D' },
  { key: '30d', label: '30D' },
  { key: 'mtd', label: 'MTD' },
  { key: 'ytd', label: 'YTD' },
]
const defaultWidgets = [
  'overviewCards',
  'performanceCards',
  'dailyPnl',
  'winsLosses',
  'cumulativePnl',
  'symbolPnl',
  'miniAnalytics',
  'processAnalytics',
  'detailTabs',
]
const defaultPanelOrder = ['dailyPnl', 'winsLosses', 'cumulativePnl', 'symbolPnl', 'miniAnalytics']
const widgetOptions = [
  { id: 'overviewCards', label: 'Overview Cards' },
  { id: 'performanceCards', label: 'Performance Cards' },
  { id: 'dailyPnl', label: 'Daily Realized PnL' },
  { id: 'winsLosses', label: 'Daily Wins / Losses' },
  { id: 'cumulativePnl', label: 'Cumulative PnL' },
  { id: 'symbolPnl', label: 'PnL by Symbol' },
  { id: 'miniAnalytics', label: 'Closed Trade Analytics' },
  { id: 'processAnalytics', label: 'Process Analytics' },
  { id: 'detailTabs', label: 'Detail Tabs' },
]

const FILTER_PLACEHOLDERS = {
  account: new Set(['all accounts', 'all account', 'accounts', 'all']),
  symbol: new Set(['all symbols', 'all symbol', 'symbols', 'all']),
  strategy: new Set(['all strategies', 'all strategy', 'strategies', 'all']),
  asset_class: new Set(['all asset classes', 'all asset class', 'asset classes', 'all']),
  date_from: new Set(['all dates', 'all date', 'dates', 'all', 'custom']),
  date_to: new Set(['all dates', 'all date', 'dates', 'all', 'custom']),
}

function sanitizeFilterValue(key, rawValue) {
  if (rawValue === null || rawValue === undefined) return ''
  const value = String(rawValue).trim()
  if (!value) return ''

  const normalized = value.toLowerCase()
  if (['null', 'undefined', 'none', 'nan'].includes(normalized)) return ''

  const placeholders = FILTER_PLACEHOLDERS[key]
  if (placeholders?.has(normalized)) return ''

  return value
}

function normalizeFilters(value = {}) {
  const merged = { ...DEFAULT_FILTERS, ...(value || {}) }
  return Object.fromEntries(
    Object.keys(DEFAULT_FILTERS).map((key) => [key, sanitizeFilterValue(key, merged[key])]),
  )
}

function normalizePanelOrder(value = []) {
  const source = Array.isArray(value) && value.length ? value : defaultPanelOrder
  const seen = new Set()
  const ordered = []
  for (const item of [...source, ...defaultPanelOrder]) {
    if (!item || seen.has(item)) continue
    seen.add(item)
    ordered.push(item)
  }
  return ordered
}

function normalizeWidgets(value = []) {
  const source = Array.isArray(value) && value.length ? value : defaultWidgets
  return defaultWidgets.filter((id) => source.includes(id))
}


function emptyStats() {
  return {
    trade_count: 0,
    open_positions: 0,
    total_realized_pnl: '0',
    total_commission: '0',
    closed_trade_count: 0,
    winning_trade_count: 0,
    losing_trade_count: 0,
    win_rate: '0',
    avg_win: '0',
    avg_loss: '0',
    avg_pnl_per_trade: '0',
    expectancy: '0',
    largest_win: '0',
    largest_loss: '0',
    avg_hold_minutes: '0',
    profit_factor: null,
    pnl_ratio: null,
    charts: {
      pnl_trend: [],
      cumulative_pnl: [],
      status_breakdown: {},
      symbol_pnl: [],
      daily_wins_losses: [],
      pnl_by_setup: [],
      win_rate_by_setup: [],
      avg_r_by_setup: [],
      pnl_by_session: [],
      overnight_vs_intraday_pnl: [],
      first_vs_later_pnl: [],
      same_symbol_repeated_performance: [],
      mistake_tag_ranking: [],
      rule_violations_count: 0,
      early_exit_rate: 0,
      over_hold_rate: 0,
    },
  }
}

function normalizeDateValueChart(source, labelKey = 'date', valueKey = 'realized_pnl') {
  if (Array.isArray(source)) {
    return source.map((item) => ({
      [labelKey]: String(item?.[labelKey] ?? item?.date ?? item?.label ?? ''),
      [valueKey]: Number(item?.[valueKey] ?? item?.value ?? item?.realized_pnl ?? 0),
    })).filter((item) => item[labelKey])
  }
  if (source && typeof source === 'object' && Array.isArray(source.labels) && Array.isArray(source.values)) {
    return source.labels.map((label, index) => ({
      [labelKey]: String(label ?? ''),
      [valueKey]: Number(source.values[index] ?? 0),
    })).filter((item) => item[labelKey])
  }
  return []
}

function normalizeWinsLossesChart(source) {
  if (Array.isArray(source)) {
    return source.map((item) => ({
      date: String(item?.date ?? item?.label ?? ''),
      wins: Number(item?.wins ?? 0),
      losses: Number(item?.losses ?? 0),
    })).filter((item) => item.date)
  }
  if (source && typeof source === 'object' && Array.isArray(source.labels)) {
    return source.labels.map((label, index) => ({
      date: String(label ?? ''),
      wins: Number(source.wins?.[index] ?? 0),
      losses: Number(source.losses?.[index] ?? 0),
    })).filter((item) => item.date)
  }
  return []
}

function normalizeSymbolPnlChart(source, fallbackSource = null) {
  const raw = source ?? fallbackSource
  if (Array.isArray(raw)) {
    return raw.map((item) => ({
      symbol: String(item?.symbol ?? item?.label ?? ''),
      realized_pnl: Number(item?.realized_pnl ?? item?.value ?? 0),
    })).filter((item) => item.symbol)
  }
  if (raw && typeof raw === 'object' && Array.isArray(raw.labels) && Array.isArray(raw.values)) {
    return raw.labels.map((label, index) => ({
      symbol: String(label ?? ''),
      realized_pnl: Number(raw.values[index] ?? 0),
    })).filter((item) => item.symbol)
  }
  return []
}

function normalizeDashboardStats(raw = null) {
  const base = emptyStats()
  const source = raw && typeof raw === 'object' ? raw : {}
  const summary = source.summary && typeof source.summary === 'object' ? source.summary : {}
  const charts = source.charts && typeof source.charts === 'object' ? source.charts : {}

  const normalized = {
    ...base,
    ...summary,
    ...source,
  }

  normalized.trade_count = Number(normalized.trade_count ?? normalized.trade_groups ?? 0)
  normalized.trade_groups = Number(normalized.trade_groups ?? normalized.trade_count ?? 0)
  normalized.open_positions = Number(normalized.open_positions ?? 0)
  normalized.total_realized_pnl = Number(normalized.total_realized_pnl ?? summary.total_realized_pnl ?? 0)
  normalized.total_commission = Number(normalized.total_commission ?? normalized.commission_total ?? summary.total_commission ?? summary.commission_total ?? 0)
  normalized.avg_pnl_per_trade = Number(normalized.avg_pnl_per_trade ?? normalized.per_trade_avg_pnl ?? summary.avg_pnl_per_trade ?? summary.per_trade_avg_pnl ?? 0)
  normalized.per_trade_avg_pnl = Number(normalized.per_trade_avg_pnl ?? normalized.avg_pnl_per_trade ?? 0)
  normalized.win_rate = Number(normalized.win_rate ?? 0)
  normalized.profit_factor = normalized.profit_factor == null ? null : Number(normalized.profit_factor)
  normalized.expectancy = Number(normalized.expectancy ?? normalized.avg_pnl_per_trade ?? 0)
  normalized.wins = Number(normalized.wins ?? normalized.winning_trade_count ?? 0)
  normalized.losses = Number(normalized.losses ?? normalized.losing_trade_count ?? 0)
  normalized.avg_win = Number(normalized.avg_win ?? 0)
  normalized.avg_loss = Number(normalized.avg_loss ?? 0)
  normalized.largest_win = Number(normalized.largest_win ?? 0)
  normalized.largest_loss = Number(normalized.largest_loss ?? 0)

  normalized.charts = {
    pnl_trend: normalizeDateValueChart(charts.pnl_trend ?? charts.daily_realized_pnl),
    cumulative_pnl: normalizeDateValueChart(charts.cumulative_pnl ?? charts.cumulative_pnl_legacy),
    daily_wins_losses: normalizeWinsLossesChart(charts.daily_wins_losses),
    symbol_pnl: normalizeSymbolPnlChart(charts.symbol_pnl, charts.pnl_by_symbol),
    status_breakdown: charts.status_breakdown && typeof charts.status_breakdown === 'object' ? charts.status_breakdown : {},
    pnl_by_setup: normalizeDateValueChart(charts.pnl_by_setup, 'date', 'realized_pnl'),
    win_rate_by_setup: normalizeDateValueChart(charts.win_rate_by_setup, 'date', 'realized_pnl'),
    avg_r_by_setup: normalizeDateValueChart(charts.avg_r_by_setup, 'date', 'realized_pnl'),
    pnl_by_session: normalizeDateValueChart(charts.pnl_by_session, 'date', 'realized_pnl'),
    overnight_vs_intraday_pnl: normalizeDateValueChart(charts.overnight_vs_intraday_pnl, 'date', 'realized_pnl'),
    first_vs_later_pnl: normalizeDateValueChart(charts.first_vs_later_pnl, 'date', 'realized_pnl'),
    same_symbol_repeated_performance: normalizeDateValueChart(charts.same_symbol_repeated_performance, 'date', 'realized_pnl'),
    mistake_tag_ranking: Array.isArray(charts.mistake_tag_ranking) ? charts.mistake_tag_ranking : [],
    rule_violations_count: Number(charts.rule_violations_count ?? 0),
    early_exit_rate: Number(charts.early_exit_rate ?? 0),
    over_hold_rate: Number(charts.over_hold_rate ?? 0),
  }

  return normalized
}

function refreshChartLayouts() {
  nextTick(() => {
    window.dispatchEvent(new Event('resize'))
    requestAnimationFrame(() => window.dispatchEvent(new Event('resize')))
    setTimeout(() => window.dispatchEvent(new Event('resize')), 80)
    setTimeout(() => window.dispatchEvent(new Event('resize')), 220)
  })
}

function safeClone(value, fallback = null) {
  try {
    return JSON.parse(JSON.stringify(value))
  } catch {
    return fallback
  }
}

function loadDashboardStateMap() {
  if (typeof window === 'undefined') return {}
  try {
    const raw = JSON.parse(window.localStorage.getItem(accountStorageKey(DASHBOARD_STATE_KEY)) || '{}')
    return raw && typeof raw === 'object' ? raw : {}
  } catch {
    return {}
  }
}

function saveDashboardStateMap(nextMap) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(accountStorageKey(DASHBOARD_STATE_KEY), JSON.stringify(nextMap || {}))
  } catch {
    // ignore storage errors
  }
}

function loadUpgradedWidgetTabs() {
  try {
    const raw = JSON.parse(localStorage.getItem(DASHBOARD_WIDGET_SCHEMA_KEY) || '[]')
    return new Set(Array.isArray(raw) ? raw.map(String) : [])
  } catch {
    return new Set()
  }
}

function saveUpgradedWidgetTabs(tabIds) {
  localStorage.setItem(DASHBOARD_WIDGET_SCHEMA_KEY, JSON.stringify([...tabIds]))
}

async function upgradeLegacyWidgetVisibility() {
  const upgraded = loadUpgradedWidgetTabs()
  const legacyTabs = tabs.value.filter((tab) => !upgraded.has(String(tab.id)) && !normalizeWidgets(tab.visible_widgets).includes('miniAnalytics'))
  if (!legacyTabs.length) return

  for (const tab of legacyTabs) {
    const nextWidgets = [...normalizeWidgets(tab.visible_widgets), 'miniAnalytics']
    replaceTab(tab.id, { ...tab, visible_widgets: nextWidgets })
    try {
      const res = await updateDashboardTab(tab.id, { visible_widgets: nextWidgets })
      replaceTab(tab.id, res.data)
    } catch {
      // keep the optimistic local state; local fallback is handled in api/common.js
    }
    upgraded.add(String(tab.id))
  }

  saveUpgradedWidgetTabs(upgraded)
}

function normalizeTab(tab = {}, index = 0) {
  return {
    ...tab,
    id: tab.id,
    name: tab.name || `Dashboard ${index + 1}`,
    sort_order: Number.isFinite(Number(tab.sort_order)) ? Number(tab.sort_order) : index,
    visible_widgets: normalizeWidgets(tab.visible_widgets),
    filters: normalizeFilters(tab.filters),
    panel_order: normalizePanelOrder(tab.panel_order),
  }
}

const tabs = ref([])
const selectedTabId = ref(null)
const preferences = ref({ default_dashboard_tab: null, default_date_range: 'all' })
const widgetPanelOpen = ref(false)
const filterPanelOpen = ref(false)
const DASHBOARD_SIDEBAR_PIN_KEY = 'ibkr-dashboard-sidebar-pinned'

function readSidebarPinned() {
  if (typeof window === 'undefined') return false
  try {
    return window.localStorage.getItem(DASHBOARD_SIDEBAR_PIN_KEY) === '1'
  } catch {
    return false
  }
}

function persistSidebarPinned(value) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(DASHBOARD_SIDEBAR_PIN_KEY, value ? '1' : '0')
  } catch {
    // ignore localStorage failures
  }
}

const sidebarPinned = ref(readSidebarPinned())
const sidebarExpanded = ref(sidebarPinned.value)
const isSidebarExpanded = computed(() => sidebarPinned.value || sidebarExpanded.value)
const activeQuickRange = ref('all')
const detailTab = ref('latest')
const latestPage = ref(1)
const closedPage = ref(1)
const rows = ref([])
const closedRows = ref([])
const latestCount = ref(0)
const closedCount = ref(0)
const detailPageSize = 5
const draggingPanelId = ref(null)

const route = useRoute()
const { activeAccountCode } = useAccounts()
const filters = reactive({ ...DEFAULT_FILTERS })
const filterOptions = ref({ accounts: [], symbols: [], strategies: [], asset_classes: [] })
const filterOptionsLoaded = ref(false)
const filterOptionsLoading = ref(false)
let filterOptionsPromise = null
const stats = ref(emptyStats())
const isDashboardLoading = ref(false)
const dashboardHydrated = ref(false)

const activeTab = computed(() => {
  return tabs.value.find((item) => String(item.id) === String(selectedTabId.value)) || tabs.value[0] || null
})
const selectedAccountLabel = computed(() => activeAccountCode.value || 'No Account')
const dateSummaryLabel = computed(() => {
  if (filters.date_from && filters.date_to) return `${filters.date_from} → ${filters.date_to}`
  if (filters.date_from) return `${filters.date_from} → Now`
  if (filters.date_to) return `Until ${filters.date_to}`
  return 'All Dates'
})
const pnlCategories = computed(() => (stats.value.charts?.pnl_trend || []).map((item) => item.date.slice(5)))
const pnlSeries = computed(() => [{ name: 'Daily PnL', color: '#22c55e', data: (stats.value.charts?.pnl_trend || []).map((item) => Number(item.realized_pnl)) }])
const cumulativeCategories = computed(() => (stats.value.charts?.cumulative_pnl || []).map((item) => item.date.slice(5)))
const cumulativeSeries = computed(() => [{ name: 'Cumulative PnL', color: '#2563eb', data: (stats.value.charts?.cumulative_pnl || []).map((item) => Number(item.realized_pnl)) }])
const winsLossCategories = computed(() => (stats.value.charts?.daily_wins_losses || []).map((item) => item.date.slice(5)))
const winsLossSeries = computed(() => [
  { name: 'Wins', color: '#22c55e', data: (stats.value.charts?.daily_wins_losses || []).map((item) => Number(item.wins || 0)) },
  { name: 'Losses', color: '#ef4444', data: (stats.value.charts?.daily_wins_losses || []).map((item) => Number(item.losses || 0)) },
])
const symbolCategories = computed(() => (stats.value.charts?.symbol_pnl || []).map((item) => item.symbol))
const symbolSeries = computed(() => [{ name: 'Realized PnL', color: '#f59e0b', data: (stats.value.charts?.symbol_pnl || []).map((item) => Number(item.realized_pnl)) }])
const setupCategories = computed(() => (stats.value.charts?.pnl_by_setup || []).map((item) => item.date))
const setupPnlSeries = computed(() => [{ name: 'PnL', color: '#14b8a6', data: (stats.value.charts?.pnl_by_setup || []).map((item) => Number(item.realized_pnl)) }])
const setupWinRateSeries = computed(() => [{ name: 'Win Rate %', color: '#22c55e', data: (stats.value.charts?.win_rate_by_setup || []).map((item) => Number(item.realized_pnl)) }])
const setupAvgRSeries = computed(() => [{ name: 'Avg R', color: '#6366f1', data: (stats.value.charts?.avg_r_by_setup || []).map((item) => Number(item.realized_pnl)) }])
const sessionCategories = computed(() => (stats.value.charts?.pnl_by_session || []).map((item) => item.date))
const sessionPnlSeries = computed(() => [{ name: 'PnL', color: '#f97316', data: (stats.value.charts?.pnl_by_session || []).map((item) => Number(item.realized_pnl)) }])
const overnightCategories = computed(() => (stats.value.charts?.overnight_vs_intraday_pnl || []).map((item) => item.date))
const overnightSeries = computed(() => [{ name: 'PnL', color: '#0ea5e9', data: (stats.value.charts?.overnight_vs_intraday_pnl || []).map((item) => Number(item.realized_pnl)) }])
const firstLaterCategories = computed(() => (stats.value.charts?.first_vs_later_pnl || []).map((item) => item.date))
const firstLaterSeries = computed(() => [{ name: 'PnL', color: '#eab308', data: (stats.value.charts?.first_vs_later_pnl || []).map((item) => Number(item.realized_pnl)) }])
const topMistakeTag = computed(() => {
  const first = stats.value.charts?.mistake_tag_ranking?.[0]
  return first ? `${first.label} (${first.count})` : '-'
})
const secondMistakeTag = computed(() => {
  const second = stats.value.charts?.mistake_tag_ranking?.[1]
  return second ? `${second.label} (${second.count})` : '-'
})
const repeatedSymbolPnl = computed(() => {
  const item = (stats.value.charts?.same_symbol_repeated_performance || []).find((entry) => entry.date === 'repeated_symbol')
  return item ? Number(item.realized_pnl) : 0
})
const orderedPanels = computed(() => {
  const panelIds = normalizePanelOrder(activeTab.value?.panel_order)
  return panelIds.map((id) => ({ id })).filter((panel) => showWidget(panel.id))
})

const pendingRequestToken = ref(0)
let routeRefreshTimer = null

function restoreDashboardSnapshot(tabId = selectedTabId.value, { restoreFilters = true } = {}) {
  const nextTabId = tabId == null ? null : String(tabId)
  if (!nextTabId) return false
  const stateMap = loadDashboardStateMap()
  const snapshot = stateMap[nextTabId]
  if (!snapshot || typeof snapshot !== 'object') return false

  if (restoreFilters && snapshot.filters) {
    Object.assign(filters, normalizeFilters(snapshot.filters))
  }
  activeQuickRange.value = snapshot.activeQuickRange || 'all'
  detailTab.value = snapshot.detailTab || 'latest'
  latestPage.value = Number.isFinite(Number(snapshot.latestPage)) ? Number(snapshot.latestPage) : 1
  closedPage.value = Number.isFinite(Number(snapshot.closedPage)) ? Number(snapshot.closedPage) : 1
  rows.value = Array.isArray(snapshot.rows) ? snapshot.rows : []
  closedRows.value = Array.isArray(snapshot.closedRows) ? snapshot.closedRows : []
  latestCount.value = Number.isFinite(Number(snapshot.latestCount)) ? Number(snapshot.latestCount) : rows.value.length
  closedCount.value = Number.isFinite(Number(snapshot.closedCount)) ? Number(snapshot.closedCount) : closedRows.value.length
  stats.value = normalizeDashboardStats(snapshot.stats)
  updateQuickRangeState()
  dashboardHydrated.value = true
  refreshChartLayouts()
  return true
}

function persistDashboardSnapshot(tabId = selectedTabId.value) {
  const nextTabId = tabId == null ? null : String(tabId)
  if (!nextTabId) return
  const stateMap = loadDashboardStateMap()
  stateMap[nextTabId] = {
    filters: safeClone(filters, { ...DEFAULT_FILTERS }),
    activeQuickRange: activeQuickRange.value,
    detailTab: detailTab.value,
    latestPage: latestPage.value,
    closedPage: closedPage.value,
    rows: safeClone(rows.value, []),
    closedRows: safeClone(closedRows.value, []),
    latestCount: latestCount.value,
    closedCount: closedCount.value,
    stats: safeClone(stats.value, emptyStats()),
    savedAt: Date.now(),
  }
  saveDashboardStateMap(stateMap)
}

function persistTabFilters(tabId = selectedTabId.value) {
  const nextTab = tabs.value.find((item) => String(item.id) === String(tabId))
  if (!nextTab) return
  replaceTab(nextTab.id, { ...nextTab, filters: { ...filters } })
  persistDashboardSnapshot(nextTab.id)
}

function scheduleRouteRefresh() {
  if (routeRefreshTimer) window.clearTimeout(routeRefreshTimer)
  routeRefreshTimer = window.setTimeout(() => {
    if (route.name === 'dashboard') loadData({ keepExisting: true })
  }, 0)
}

function handleSidebarMouseEnter() {
  if (!sidebarPinned.value) sidebarExpanded.value = true
  ensureFilterOptionsLoaded()
}

function handleSidebarMouseLeave() {
  if (!sidebarPinned.value) sidebarExpanded.value = false
}

function toggleSidebarHandle() {
  if (sidebarPinned.value) return
  sidebarExpanded.value = !sidebarExpanded.value
  if (sidebarExpanded.value) ensureFilterOptionsLoaded()
}

function toggleSidebarPinned() {
  sidebarPinned.value = !sidebarPinned.value
  persistSidebarPinned(sidebarPinned.value)
  sidebarExpanded.value = sidebarPinned.value
  if (sidebarPinned.value) ensureFilterOptionsLoaded()
}

function replaceTab(tabId, nextTab) {
  tabs.value = tabs.value.map((item, index) => (String(item.id) === String(tabId) ? normalizeTab(nextTab, index) : item))
}

function cloneTabForPayload(tab) {
  return {
    name: tab.name,
    sort_order: tab.sort_order,
    visible_widgets: normalizeWidgets(tab.visible_widgets),
    filters: normalizeFilters(tab.filters),
    panel_order: normalizePanelOrder(tab.panel_order),
  }
}

function formatPercent(value) {
  return value === null || value === undefined ? '-' : `${value}%`
}

function openDatePicker(event) {
  const dateInput = event?.target
  if (dateInput && typeof dateInput.showPicker === 'function') dateInput.showPicker()
}

function toDateInput(date) {
  return date.toISOString().slice(0, 10)
}

function updateQuickRangeState() {
  if (!filters.date_from && !filters.date_to) {
    activeQuickRange.value = 'all'
    return
  }
  activeQuickRange.value = ''
}

async function loadPreferences() {
  try {
    const res = await fetchDashboardPreferences()
    preferences.value = {
      default_dashboard_tab: res.data?.default_dashboard_tab ?? null,
      default_date_range: res.data?.default_date_range || 'all',
    }
  } catch {
    preferences.value = { default_dashboard_tab: null, default_date_range: 'all' }
  }
}

async function loadTabs() {
  const res = await fetchDashboardTabs()
  const rawTabs = Array.isArray(res.data) ? res.data : (res.data?.results || [])
  tabs.value = rawTabs.map((tab, index) => normalizeTab(tab, index))

  const storedSelection = localStorage.getItem(accountStorageKey(DASHBOARD_SELECTED_KEY))
  const candidateSelection = storedSelection || preferences.value.default_dashboard_tab || tabs.value[0]?.id || null
  const selected = tabs.value.find((item) => String(item.id) === String(candidateSelection))?.id || tabs.value[0]?.id || null
  selectedTabId.value = selected
  localStorage.setItem(accountStorageKey(DASHBOARD_SELECTED_KEY), String(selected || ''))
  syncFiltersFromTab(true)
}

function syncFiltersFromTab(applyDefaultRange = false, preferSnapshot = false) {
  const tab = activeTab.value
  if (!tab) {
    Object.assign(filters, DEFAULT_FILTERS)
    activeQuickRange.value = 'all'
    return
  }

  if (!(preferSnapshot && restoreDashboardSnapshot(tab.id, { restoreFilters: true }))) {
    Object.assign(filters, normalizeFilters(tab.filters))
  }
  if (applyDefaultRange && !filters.date_from && !filters.date_to && preferences.value.default_date_range && preferences.value.default_date_range !== 'all') {
    applyQuickRange(preferences.value.default_date_range, false)
    return
  }
  updateQuickRangeState()
}

async function saveActiveTab(partial = {}) {
  const tab = activeTab.value
  if (!tab) return null
  const payload = normalizeTab({ ...cloneTabForPayload(tab), ...partial }, tab.sort_order)
  const res = await updateDashboardTab(tab.id, payload)
  replaceTab(tab.id, res.data)
  return res.data
}

function currentParams() {
  const params = {}
  if (filters.date_from) params.date_from = filters.date_from
  if (filters.date_to) params.date_to = filters.date_to
  if (filters.account) params.account = filters.account
  if (filters.symbol) params.symbol = filters.symbol
  if (filters.strategy) params.strategy = filters.strategy
  if (filters.asset_class) params.asset_class = filters.asset_class
  return params
}

function detailPagingParams(page) {
  return {
    ...currentParams(),
    page,
    page_size: detailPageSize,
  }
}

async function fetchLatestRows(page) {
  return fetchTradeGroups(detailPagingParams(page))
}

async function fetchClosedAnalyticsRows(page) {
  return fetchClosedTradeAnalytics(detailPagingParams(page))
}

async function loadRows(nextPage = latestPage.value) {
  latestPage.value = nextPage
  try {
    const groupsRes = await fetchLatestRows(latestPage.value)
    rows.value = responseRows(groupsRes.data)
    latestCount.value = responseCount(groupsRes.data, rows.value)
  } catch (err) {
    if (err?.response?.status === 404 && latestPage.value > 1) {
      latestPage.value = 1
      const groupsRes = await fetchLatestRows(1)
      rows.value = responseRows(groupsRes.data)
      latestCount.value = responseCount(groupsRes.data, rows.value)
      return
    }
    throw err
  }
}

async function loadClosedRows(nextPage = closedPage.value) {
  closedPage.value = nextPage
  try {
    const res = await fetchClosedAnalyticsRows(closedPage.value)
    closedRows.value = responseRows(res.data)
    closedCount.value = responseCount(res.data, closedRows.value)
  } catch (err) {
    if (err?.response?.status === 404 && closedPage.value > 1) {
      closedPage.value = 1
      const res = await fetchClosedAnalyticsRows(1)
      closedRows.value = responseRows(res.data)
      closedCount.value = responseCount(res.data, closedRows.value)
      return
    }
    throw err
  }
}

async function loadDashboard() {
  const dashboardRes = await fetchTradeDashboard(currentParams())
  stats.value = dashboardRes.data
}

async function loadFilterOptions({ force = false } = {}) {
  if (filterOptionsLoaded.value && !force) return filterOptions.value
  if (filterOptionsPromise && !force) return filterOptionsPromise

  filterOptionsLoading.value = true
  filterOptionsPromise = fetchTradeFilterOptions()
    .then((res) => {
      filterOptions.value = res?.data || {
        accounts: [],
        symbols: [],
        strategies: [],
        asset_classes: [],
      }
      filterOptionsLoaded.value = true
      return filterOptions.value
    })
    .catch((err) => {
      console.error('Failed to load dashboard filter options:', err)
      filterOptions.value = { accounts: [], symbols: [], strategies: [], asset_classes: [] }
      throw err
    })
    .finally(() => {
      filterOptionsLoading.value = false
      filterOptionsPromise = null
    })

  return filterOptionsPromise
}

function ensureFilterOptionsLoaded() {
  if (!filterOptionsLoaded.value && !filterOptionsLoading.value) {
    void loadFilterOptions()
  }
}

async function loadData({ keepExisting = true } = {}) {
  const requestToken = pendingRequestToken.value + 1
  pendingRequestToken.value = requestToken
  isDashboardLoading.value = true

  const [dashboardRes, rowsRes, closedRes] = await Promise.allSettled([
    fetchTradeDashboard(currentParams()),
    fetchLatestRows(latestPage.value),
    fetchClosedAnalyticsRows(closedPage.value),
  ])

  if (requestToken !== pendingRequestToken.value) return

  if (dashboardRes.status === 'fulfilled') {
    stats.value = normalizeDashboardStats(dashboardRes.value.data)
  } else if (!keepExisting && !dashboardHydrated.value) {
    stats.value = emptyStats()
  }

  if (rowsRes.status === 'fulfilled') {
    rows.value = responseRows(rowsRes.value.data)
    latestCount.value = responseCount(rowsRes.value.data, rows.value)
  } else if (!keepExisting && !dashboardHydrated.value) {
    rows.value = []
    latestCount.value = 0
  }

  if (closedRes.status === 'fulfilled') {
    closedRows.value = responseRows(closedRes.value.data)
    closedCount.value = responseCount(closedRes.value.data, closedRows.value)
  } else if (!keepExisting && !dashboardHydrated.value) {
    closedRows.value = []
    closedCount.value = 0
  }

  dashboardHydrated.value = true
  isDashboardLoading.value = false
  persistDashboardSnapshot()
  refreshChartLayouts()
}

async function applyQuickRange(key, reload = true) {
  activeQuickRange.value = key
  const now = new Date()
  if (key === 'all') {
    filters.date_from = ''
    filters.date_to = ''
  } else if (key === '7d') {
    const start = new Date(now)
    start.setDate(now.getDate() - 6)
    filters.date_from = toDateInput(start)
    filters.date_to = toDateInput(now)
  } else if (key === '30d') {
    const start = new Date(now)
    start.setDate(now.getDate() - 29)
    filters.date_from = toDateInput(start)
    filters.date_to = toDateInput(now)
  } else if (key === 'mtd') {
    const start = new Date(now.getFullYear(), now.getMonth(), 1)
    filters.date_from = toDateInput(start)
    filters.date_to = toDateInput(now)
  } else if (key === 'ytd') {
    const start = new Date(now.getFullYear(), 0, 1)
    filters.date_from = toDateInput(start)
    filters.date_to = toDateInput(now)
  }

  latestPage.value = 1
  closedPage.value = 1
  if (activeTab.value) {
    await saveActiveTab({ filters: { ...filters } })
  }
  if (reload) await loadData()
}

async function applyFilters() {
  filters.account = activeAccountCode.value
  latestPage.value = 1
  closedPage.value = 1
  filterPanelOpen.value = false
  updateQuickRangeState()
  persistTabFilters()
  if (activeTab.value) {
    await saveActiveTab({ filters: { ...filters } })
  }
  await loadData({ keepExisting: true })
}

async function resetFilters() {
  Object.assign(filters, DEFAULT_FILTERS)
  filters.account = activeAccountCode.value
  activeQuickRange.value = preferences.value.default_date_range || 'all'
  latestPage.value = 1
  closedPage.value = 1
  filterPanelOpen.value = false
  persistTabFilters()
  if (preferences.value.default_date_range && preferences.value.default_date_range !== 'all') {
    await applyQuickRange(preferences.value.default_date_range)
    return
  }
  if (activeTab.value) {
    await saveActiveTab({ filters: { ...filters } })
  }
  await loadData({ keepExisting: true })
}

async function selectTab(tabId) {
  const nextTab = tabs.value.find((item) => String(item.id) === String(tabId))
  if (!nextTab) return
  selectedTabId.value = nextTab.id
  localStorage.setItem(accountStorageKey(DASHBOARD_SELECTED_KEY), String(nextTab.id))
  latestPage.value = 1
  closedPage.value = 1
  const restored = restoreDashboardSnapshot(nextTab.id, { restoreFilters: true })
  if (!restored) syncFiltersFromTab(true, false)
  else updateQuickRangeState()
  await loadData({ keepExisting: true })
}

async function createTab() {
  const name = window.prompt('New dashboard tab name')
  if (!name) return
  const payload = {
    name,
    sort_order: tabs.value.length,
    visible_widgets: [...defaultWidgets],
    filters: { ...filters },
    panel_order: [...normalizePanelOrder(activeTab.value?.panel_order)],
  }
  const res = await createDashboardTab(payload)
  tabs.value = [...tabs.value, normalizeTab(res.data, tabs.value.length)]
  await selectTab(res.data.id)
}

async function renameTab() {
  if (!activeTab.value) return
  const name = window.prompt('Rename dashboard tab', activeTab.value.name)
  if (!name) return
  const res = await updateDashboardTab(activeTab.value.id, { name })
  replaceTab(activeTab.value.id, res.data)
}

async function deleteTab() {
  if (tabs.value.length <= 1 || !activeTab.value) return
  if (!window.confirm(`Delete dashboard tab "${activeTab.value.name}"?`)) return

  const deleteId = activeTab.value.id
  await deleteDashboardTab(deleteId)
  tabs.value = tabs.value.filter((item) => String(item.id) !== String(deleteId))

  const nextId = tabs.value[0]?.id || null
  if (String(preferences.value.default_dashboard_tab) === String(deleteId)) {
    await saveDashboardPreference({ default_dashboard_tab: nextId || null })
  }
  if (nextId) {
    await selectTab(nextId)
  }
}

async function saveDashboardPreference(patch) {
  const res = await saveDashboardPreferences(patch)
  preferences.value = {
    ...preferences.value,
    ...(res.data || {}),
  }
}

function showWidget(widgetId) {
  return normalizeWidgets(activeTab.value?.visible_widgets).includes(widgetId)
}

async function toggleWidget(widgetId) {
  if (!activeTab.value) return
  const widgets = new Set(normalizeWidgets(activeTab.value.visible_widgets))
  if (widgets.has(widgetId)) widgets.delete(widgetId)
  else widgets.add(widgetId)

  const nextWidgets = defaultWidgets.filter((id) => widgets.has(id))
  replaceTab(activeTab.value.id, { ...activeTab.value, visible_widgets: nextWidgets })
  await saveActiveTab({ visible_widgets: nextWidgets })

  const upgraded = loadUpgradedWidgetTabs()
  upgraded.add(String(activeTab.value.id))
  saveUpgradedWidgetTabs(upgraded)
}

function onPanelDragStart(panelId) {
  draggingPanelId.value = panelId
}

async function onPanelDrop(targetId) {
  if (!activeTab.value || !draggingPanelId.value || draggingPanelId.value === targetId) return
  const current = [...normalizePanelOrder(activeTab.value.panel_order)]
  const from = current.indexOf(draggingPanelId.value)
  const to = current.indexOf(targetId)
  if (from < 0 || to < 0) return
  const [item] = current.splice(from, 1)
  current.splice(to, 0, item)
  draggingPanelId.value = null
  replaceTab(activeTab.value.id, { ...activeTab.value, panel_order: current })
  await saveActiveTab({ panel_order: current })
}

onMounted(async () => {
  const routeSelectedId = typeof window !== 'undefined'
    ? window.localStorage.getItem(accountStorageKey(DASHBOARD_SELECTED_KEY))
    : null
  await loadPreferences()
  await loadTabs()
  if (routeSelectedId) restoreDashboardSnapshot(routeSelectedId, { restoreFilters: false })
  syncFiltersFromTab(true, true)
  filters.account = activeAccountCode.value
  await loadData({ keepExisting: true })
  void upgradeLegacyWidgetVisibility()
})

watch(
  () => route.name,
  (name, oldName) => {
    if (name === 'dashboard' && oldName && oldName !== 'dashboard') {
      void loadData({ keepExisting: true })
    }
  }
)

watch(sidebarExpanded, () => {
  refreshChartLayouts()
})

onBeforeUnmount(() => {
  pendingRequestToken.value += 1
  persistDashboardSnapshot()
  if (routeRefreshTimer) {
    window.clearTimeout(routeRefreshTimer)
    routeRefreshTimer = null
  }
})
</script>
