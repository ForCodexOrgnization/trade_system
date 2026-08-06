export const ACTIVE_ACCOUNT_STORAGE_KEY = 'ibkr-active-account-v1'

export function readActiveAccountCode() {
  if (typeof window === 'undefined') return ''
  try {
    return window.localStorage.getItem(ACTIVE_ACCOUNT_STORAGE_KEY) || ''
  } catch {
    return ''
  }
}

export function writeActiveAccountCode(accountCode) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(ACTIVE_ACCOUNT_STORAGE_KEY, accountCode || '')
  } catch {
    // Account selection still works for this session when storage is unavailable.
  }
}
