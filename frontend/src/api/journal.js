import api from './client'

export const fetchJournalToday = (date) => api.get('/journal/trading-days/today/', { params: { date } })
export const createJournalToday = (payload) => api.post('/journal/trading-days/today/', payload)
export const updateTradingDay = (id, payload) => api.patch(`/journal/trading-days/${id}/`, payload)

export const createJournalSession = (payload) => api.post('/journal/sessions/', payload)
export const updateJournalSession = (id, payload) => api.patch(`/journal/sessions/${id}/`, payload)
export const startJournalSession = (id) => api.post(`/journal/sessions/${id}/start/`)
export const closeJournalSession = (id) => api.post(`/journal/sessions/${id}/close/`)
export const reviewJournalSession = (id, payload) => api.post(`/journal/sessions/${id}/review/`, payload)

export const fetchJournalCampaigns = (params = {}) => api.get('/journal/campaigns/', { params })
export const createJournalCampaign = (payload) => api.post('/journal/campaigns/', payload)
export const createDecisionSnapshot = (id, payload) => api.post(`/journal/campaigns/${id}/decision-snapshot/`, payload)
export const activateJournalCampaign = (id) => api.post(`/journal/campaigns/${id}/activate/`)
export const attachJournalFills = (id, payload) => api.post(`/journal/campaigns/${id}/attach-fills/`, payload)
export const undoJournalGrouping = (id) => api.post(`/journal/campaigns/${id}/undo-grouping/`)
export const closeJournalCampaign = (id) => api.post(`/journal/campaigns/${id}/close/`)
export const reviewJournalCampaign = (id, payload) => api.post(`/journal/campaigns/${id}/review/`, payload)
export const fetchCampaignAudit = (id) => api.get(`/journal/campaigns/${id}/audit/`)

export const importJournalFills = (file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/journal/fills/import/', form, { headers: { 'Content-Type': 'multipart/form-data' } })
}

export const fetchJournalAnalytics = () => api.get('/journal/analytics/')
