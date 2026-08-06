import api from './client'

const DASHBOARD_TABS_KEY = 'trade-dashboard-tabs-v1'

const DEFAULT_FILTERS = {
  date_from: '',
  date_to: '',
  account: '',
  symbol: '',
  strategy: '',
  asset_class: '',
}

const DEFAULT_WIDGETS = [
  'overviewCards',
  'performanceCards',
  'dailyPnl',
  'winsLosses',
  'cumulativePnl',
  'symbolPnl',
  'miniAnalytics',
  'detailTabs',
]

const DEFAULT_PANEL_ORDER = ['dailyPnl', 'winsLosses', 'cumulativePnl', 'symbolPnl', 'miniAnalytics']

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

function normalizeFilters(filters = {}) {
  return { ...DEFAULT_FILTERS, ...(filters || {}) }
}

function normalizePanelOrder(panelOrder = []) {
  const source = Array.isArray(panelOrder) && panelOrder.length ? panelOrder : DEFAULT_PANEL_ORDER
  const seen = new Set()
  const normalized = []
  for (const item of [...source, ...DEFAULT_PANEL_ORDER]) {
    if (!item || seen.has(item)) continue
    seen.add(item)
    normalized.push(item)
  }
  return normalized
}

function normalizeWidgets(visibleWidgets = []) {
  const source = Array.isArray(visibleWidgets) && visibleWidgets.length ? visibleWidgets : DEFAULT_WIDGETS
  return DEFAULT_WIDGETS.filter((id) => source.includes(id))
}

function normalizeTab(tab = {}, index = 0) {
  return {
    id: tab.id ?? `local-${index + 1}`,
    name: tab.name || `Dashboard ${index + 1}`,
    sort_order: Number.isFinite(Number(tab.sort_order)) ? Number(tab.sort_order) : index,
    visible_widgets: normalizeWidgets(tab.visible_widgets),
    filters: normalizeFilters(tab.filters),
    panel_order: normalizePanelOrder(tab.panel_order),
    created_at: tab.created_at || null,
    updated_at: tab.updated_at || null,
  }
}

function loadLocalTabs() {
  try {
    const raw = JSON.parse(localStorage.getItem(DASHBOARD_TABS_KEY) || '[]')
    if (Array.isArray(raw) && raw.length) {
      return raw.map((tab, index) => normalizeTab(tab, index))
    }
  } catch {}

  const defaults = [normalizeTab({ id: 'local-overview', name: 'Overview', sort_order: 0 }, 0)]
  saveLocalTabs(defaults)
  return defaults
}

function saveLocalTabs(tabs) {
  const normalized = (tabs || []).map((tab, index) => normalizeTab(tab, index))
  localStorage.setItem(DASHBOARD_TABS_KEY, JSON.stringify(normalized))
  return normalized
}

function localResponse(data) {
  return Promise.resolve({ data })
}

export const fetchDashboardTabs = async () => {
  try {
    return await api.get('/common/dashboard-tabs/')
  } catch {
    return localResponse(loadLocalTabs())
  }
}

export const createDashboardTab = async (payload) => {
  try {
    return await api.post('/common/dashboard-tabs/', payload)
  } catch {
    const tabs = loadLocalTabs()
    const created = normalizeTab(
      {
        ...payload,
        id: `local-${Date.now()}`,
        sort_order: tabs.length,
      },
      tabs.length,
    )
    tabs.push(created)
    saveLocalTabs(tabs)
    return localResponse(created)
  }
}

export const updateDashboardTab = async (id, payload) => {
  try {
    return await api.patch(`/common/dashboard-tabs/${id}/`, payload)
  } catch {
    const tabs = loadLocalTabs()
    const index = tabs.findIndex((tab) => String(tab.id) === String(id))
    if (index === -1) throw new Error(`Dashboard tab ${id} not found`)
    const updated = normalizeTab({ ...tabs[index], ...clone(payload), id: tabs[index].id }, index)
    tabs.splice(index, 1, updated)
    saveLocalTabs(tabs)
    return localResponse(updated)
  }
}

export const deleteDashboardTab = async (id) => {
  try {
    return await api.delete(`/common/dashboard-tabs/${id}/`)
  } catch {
    const tabs = loadLocalTabs().filter((tab) => String(tab.id) !== String(id))
    saveLocalTabs(tabs.length ? tabs : [normalizeTab({ id: 'local-overview', name: 'Overview', sort_order: 0 }, 0)])
    return localResponse(null)
  }
}

export const fetchBrokerAccounts = () => api.get('/common/broker-accounts/')
export const createBrokerAccount = (payload) => api.post('/common/broker-accounts/', payload)
export const updateBrokerAccount = (id, payload) => api.patch(`/common/broker-accounts/${id}/`, payload)
export const disableBrokerAccount = (id) => api.delete(`/common/broker-accounts/${id}/`)
export const testBrokerAccountConnection = (id) => api.post(`/common/broker-accounts/${id}/test-connection/`)
