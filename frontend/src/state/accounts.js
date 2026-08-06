import { computed, readonly, ref } from 'vue'

import { fetchBrokerAccounts } from '../api/common'
import { responseRows } from '../api/pagination'
import { readActiveAccountCode, writeActiveAccountCode } from './accountContext'

const accounts = ref([])
const activeAccountCode = ref(readActiveAccountCode())
const initialized = ref(false)
const loading = ref(false)
const error = ref('')
const accountVersion = ref(0)

function normalizeAccounts(rows = []) {
  return rows
    .filter((item) => item?.is_active && item?.account_code)
    .sort((left, right) => left.account_code.localeCompare(right.account_code))
}

function chooseActiveAccount() {
  const currentExists = accounts.value.some((item) => item.account_code === activeAccountCode.value)
  if (!currentExists) {
    activeAccountCode.value = accounts.value[0]?.account_code || ''
    writeActiveAccountCode(activeAccountCode.value)
  }
}

export async function refreshAccounts() {
  loading.value = true
  error.value = ''
  try {
    const response = await fetchBrokerAccounts()
    accounts.value = normalizeAccounts(responseRows(response.data))
    chooseActiveAccount()
    return accounts.value
  } catch (err) {
    error.value = err?.response?.data?.detail || err?.message || 'Unable to load broker accounts.'
    throw err
  } finally {
    loading.value = false
    initialized.value = true
  }
}

export async function initializeAccounts() {
  if (initialized.value || loading.value) return accounts.value
  return refreshAccounts()
}

export function selectActiveAccount(accountCode) {
  const normalized = String(accountCode || '').trim()
  if (!accounts.value.some((item) => item.account_code === normalized)) return false
  if (normalized === activeAccountCode.value) return true
  activeAccountCode.value = normalized
  writeActiveAccountCode(normalized)
  accountVersion.value += 1
  return true
}

export function useAccounts() {
  return {
    accounts: readonly(accounts),
    activeAccountCode: readonly(activeAccountCode),
    activeAccount: computed(() => accounts.value.find((item) => item.account_code === activeAccountCode.value) || null),
    initialized: readonly(initialized),
    loading: readonly(loading),
    error: readonly(error),
    accountVersion: readonly(accountVersion),
    initializeAccounts,
    refreshAccounts,
    selectActiveAccount,
  }
}
