import axios from 'axios'
import { readActiveAccountCode } from '../state/accountContext'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000,
})

function isAccountScopedRequest(url = '') {
  return url.startsWith('/trades/')
}

api.interceptors.request.use((config) => {
  if (!isAccountScopedRequest(config.url)) return config
  const account = readActiveAccountCode()
  if (!account) return config
  config.params = { ...(config.params || {}), account }
  return config
})

export default api
