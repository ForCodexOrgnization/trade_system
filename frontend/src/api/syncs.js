import api from './client'

export const startIBKRSync = () => api.post('/syncs/ibkr/start/', {}, { timeout: 900000 })
export const startLocalIBKRSync = () => api.post('/syncs/ibkr/start/', { use_local_flex_xml: true }, { timeout: 900000 })
export const startIBKRAccountSync = (accountId, useLocalFlexXml = false) => api.post(
  `/syncs/ibkr/accounts/${accountId}/start/`,
  { use_local_flex_xml: useLocalFlexXml },
  { timeout: 900000 },
)
export const fetchSyncJobs = (params = {}) => api.get('/syncs/jobs/', { params })
