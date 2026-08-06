import api from './client'

export const fetchJournalToday = (date) => api.get('/journal/trading-days/today/', { params: { date } })
export const createJournalToday = (payload) => api.post('/journal/trading-days/today/', payload)
export const updateTradingDay = (id, payload) => api.patch(`/journal/trading-days/${id}/`, payload)

export const fetchJournalContexts = (params = {}) => api.get('/journal/contexts/', { params })
export const createJournalContext = (payload) => api.post('/journal/contexts/', payload)
export const updateJournalContext = (id, payload) => api.patch(`/journal/contexts/${id}/`, payload)
export const startJournalContext = (id) => api.post(`/journal/contexts/${id}/start/`)
export const closeJournalContext = (id) => api.post(`/journal/contexts/${id}/close/`)
export const reviewJournalContext = (id, payload) => api.post(`/journal/contexts/${id}/review/`, payload)

export const fetchJournalCampaigns = (params = {}) => api.get('/journal/campaigns/', { params })
export const createJournalCampaign = (payload) => api.post('/journal/campaigns/', payload)
export const updateJournalCampaign = (id, payload) => api.patch(`/journal/campaigns/${id}/`, payload)
export const createDecisionVersion = (id, payload) => api.post(`/journal/campaigns/${id}/decision-versions/`, payload)
export const createDecisionUpdate = (id, payload) => api.post(`/journal/campaigns/${id}/decision-updates/`, payload)
export const createCorrectionRecord = (id, payload) => api.post(`/journal/campaigns/${id}/corrections/`, payload)
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
