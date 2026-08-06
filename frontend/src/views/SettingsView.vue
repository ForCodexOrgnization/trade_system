<template>
  <div>
    <div class="dashboard-hero card compact-header-card">
      <div>
        <div class="dashboard-kicker">System</div>
        <h1 class="dashboard-title">Settings</h1>
        <p class="dashboard-subtitle">查看连接状态，并把默认 dashboard tab / 日期范围保存到后端数据库。</p>
      </div>
    </div>

    <div class="settings-grid">
      <div class="card settings-card account-settings-card">
        <div class="section-title">Trading Accounts</div>
        <div class="settings-copy muted-copy">
          每个账户使用独立的 Flex Query。Token 加密保存在后端，页面只显示末四位；连接测试会拒绝包含其他账户的 Query。
        </div>

        <div class="account-config-form">
          <label>
            <span>Display Name</span>
            <input v-model.trim="accountForm.display_name" type="text" placeholder="例如：主账户" />
          </label>
          <label>
            <span>IBKR Account Code</span>
            <input v-model.trim="accountForm.account_code" :disabled="Boolean(editingAccountId)" type="text" placeholder="U12345678" />
          </label>
          <label>
            <span>Flex Query ID</span>
            <input v-model.trim="accountForm.flex_query_id" type="text" placeholder="Query ID" />
          </label>
          <label>
            <span>Flex Token</span>
            <input v-model.trim="accountForm.flex_token" type="password" :placeholder="editingAccountId ? '留空表示不修改' : 'Flex Token'" autocomplete="new-password" />
          </label>
        </div>
        <div class="settings-actions">
          <button @click="saveTradingAccount" :disabled="accountSaving || !accountForm.account_code">
            {{ accountSaving ? 'Saving...' : (editingAccountId ? 'Update Account' : 'Add Account') }}
          </button>
          <button v-if="editingAccountId" class="secondary" @click="resetAccountForm">Cancel</button>
        </div>

        <div class="account-config-list">
          <div v-for="account in brokerAccounts" :key="account.id" class="account-config-row">
            <div>
              <strong>{{ account.display_name || account.account_code }}</strong>
              <div class="muted-copy">{{ account.account_code }} · Query {{ account.flex_query_id || 'not configured' }} · Token {{ account.token_preview || 'not configured' }}</div>
              <div v-if="account.last_sync_error" class="account-error-copy">{{ account.last_sync_error }}</div>
            </div>
            <div class="account-config-status">
              <span :class="['badge', account.connection_status]">{{ account.connection_status }}</span>
              <span :class="['badge', account.is_active ? 'success' : 'failed']">{{ account.is_active ? 'active' : 'disabled' }}</span>
            </div>
            <div class="account-config-actions">
              <button class="secondary small-btn" @click="editTradingAccount(account)">Edit</button>
              <button class="secondary small-btn" @click="testTradingAccount(account)" :disabled="accountTestingId === account.id || !account.token_configured || !account.flex_query_id">
                {{ accountTestingId === account.id ? 'Testing...' : 'Test Connection' }}
              </button>
              <button class="secondary small-btn" @click="toggleTradingAccount(account)">{{ account.is_active ? 'Disable' : 'Enable' }}</button>
            </div>
          </div>
          <div v-if="!brokerAccounts.length" class="muted-copy">No trading accounts configured.</div>
        </div>
      </div>

      <AccountSyncPanel />

    </div>

    <div class="settings-reset-row">
      <span class="muted-copy">界面布局出现异常时，可恢复当前浏览器的默认布局。</span>
      <button class="secondary" @click="resetUILayout">Reset UI Layout</button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import {
  fetchBrokerAccounts,
  createBrokerAccount,
  updateBrokerAccount,
  testBrokerAccountConnection,
} from '../api/common'
import { responseRows } from '../api/pagination'
import { refreshAccounts } from '../state/accounts'
import AccountSyncPanel from '../components/AccountSyncPanel.vue'

const brokerAccounts = ref([])
const editingAccountId = ref(null)
const accountSaving = ref(false)
const accountTestingId = ref(null)
const accountForm = reactive({ display_name: '', account_code: '', flex_query_id: '', flex_token: '' })

async function loadBrokerAccounts() {
  const res = await fetchBrokerAccounts()
  brokerAccounts.value = responseRows(res.data)
}

function resetAccountForm() {
  editingAccountId.value = null
  Object.assign(accountForm, { display_name: '', account_code: '', flex_query_id: '', flex_token: '' })
}

function editTradingAccount(account) {
  editingAccountId.value = account.id
  Object.assign(accountForm, {
    display_name: account.display_name || '',
    account_code: account.account_code,
    flex_query_id: account.flex_query_id || '',
    flex_token: '',
  })
}

async function saveTradingAccount() {
  accountSaving.value = true
  try {
    const payload = {
      display_name: accountForm.display_name,
      account_code: accountForm.account_code,
      flex_query_id: accountForm.flex_query_id,
      is_active: true,
    }
    if (accountForm.flex_token) payload.flex_token = accountForm.flex_token
    if (editingAccountId.value) await updateBrokerAccount(editingAccountId.value, payload)
    else await createBrokerAccount(payload)
    resetAccountForm()
    await Promise.all([loadBrokerAccounts(), refreshAccounts()])
  } catch (err) {
    alert(err?.response?.data?.account_code?.[0] || err?.response?.data?.detail || err?.message || 'Unable to save account.')
  } finally {
    accountSaving.value = false
  }
}

async function testTradingAccount(account) {
  accountTestingId.value = account.id
  try {
    await testBrokerAccountConnection(account.id)
    await loadBrokerAccounts()
    alert(`Connection verified for ${account.account_code}.`)
  } catch (err) {
    await loadBrokerAccounts()
    alert(err?.response?.data?.error || err?.message || 'Connection test failed.')
  } finally {
    accountTestingId.value = null
  }
}

async function toggleTradingAccount(account) {
  await updateBrokerAccount(account.id, { is_active: !account.is_active })
  await Promise.all([loadBrokerAccounts(), refreshAccounts()])
}

function resetUILayout() {
  Object.keys(localStorage)
    .filter((key) => (
      key.startsWith('trade-dashboard-')
      || key.startsWith('ibkr-dashboard-')
      || key.startsWith('tv-')
      || key.startsWith('journal-')
    ))
    .forEach((key) => localStorage.removeItem(key))
  alert('UI layout reset. Reload the page to apply the default layout.')
}

onMounted(async () => {
  await loadBrokerAccounts()
})
</script>

<style scoped>
.account-settings-card { grid-column: 1 / -1; }
.account-config-form { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }
.account-config-form label { display: grid; gap: 6px; }
.account-config-list { display: grid; gap: 10px; margin-top: 18px; }
.account-config-row { display: grid; grid-template-columns: minmax(260px, 1fr) auto auto; gap: 16px; align-items: center; padding: 14px; border: 1px solid var(--line); border-radius: 12px; }
.account-config-status, .account-config-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.account-error-copy { margin-top: 5px; color: var(--negative); font-size: 12px; }
.settings-reset-row { display: flex; justify-content: flex-end; align-items: center; gap: 14px; margin-top: 18px; padding: 0 4px 18px; }
@media (max-width: 980px) {
  .account-config-form { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .account-config-row { grid-template-columns: 1fr; }
}
@media (max-width: 620px) {
  .account-config-form { grid-template-columns: 1fr; }
}
</style>
