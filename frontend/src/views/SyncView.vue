<template>
  <div>
    <div class="page-header">
      <h1>IBKR Sync</h1>
      <p>全量同步 IBKR executions。真实同步会请求 IBKR 并刷新本地 XML 缓存；本地测试同步只读取缓存，适合反复调试 grouping/dedupe/rebuild。</p>
    </div>

    <div class="card sync-action-card">
      <label class="sync-account-picker">
        <span>Sync Account</span>
        <select v-model="selectedAccountId" :disabled="loading">
          <option value="">Select a configured account</option>
          <option v-for="account in activeAccounts" :key="account.id" :value="String(account.id)">
            {{ account.display_name || account.account_code }} · {{ account.connection_status }}
          </option>
        </select>
      </label>
      <button @click="runSync('real')" :disabled="loading || !selectedAccountConfigured">
        {{ loadingMode === 'real' ? 'Syncing from IBKR...' : 'Start Real IBKR Sync' }}
      </button>
      <button class="secondary" @click="runSync('local')" :disabled="loading || !selectedAccount || !localCacheExists">
        {{ loadingMode === 'local' ? 'Syncing from local XML...' : 'Start Local Test Sync' }}
      </button>
      <p class="muted-copy">每个账户使用自己的 Flex Token、Query ID 和本地 XML 缓存。请先在 Settings 添加并验证账户。</p>
      <p v-if="selectedAccount && !selectedAccountConfigured" class="muted-copy pnl-negative">
        当前账户尚未配置 Flex Token / Query ID，请先到 Settings 完成配置。
      </p>
      <p v-if="configStatus" :class="['muted-copy', localCacheExists ? 'pnl-positive' : 'pnl-negative']">
        Selected account XML cache: {{ localCacheExists ? 'Ready' : 'Missing — run a real sync for this account first' }}
      </p>
    </div>

    <div class="card sync-action-card">
      <div class="section-title">Remove an old account</div>
      <p class="muted-copy">选择不再使用的账户并删除后，该账户的 executions、fills、trade groups 和 Dashboard 统计都会移除。此操作不可撤销；不会影响其他账户。</p>
      <div class="sync-delete-row">
        <select v-model="accountToDelete" :disabled="loading || !accounts.length">
          <option value="">Select an account</option>
          <option v-for="account in activeAccounts" :key="account.id" :value="account.account_code">{{ account.display_name || account.account_code }}</option>
        </select>
        <button class="danger" @click="removeAccountData" :disabled="loading || !accountToDelete">
          {{ loadingMode === 'delete' ? 'Removing...' : 'Remove selected account data' }}
        </button>
      </div>
    </div>

    <div v-if="result" class="card success-box">
      <div class="section-title">Latest Result</div>
      <p><strong>Job ID:</strong> {{ result.job_id }}</p>
      <p><strong>Raw Count:</strong> {{ result.result.raw_count }}</p>
      <p><strong>Inserted:</strong> {{ result.result.inserted_count }}</p>
      <p><strong>Duplicates:</strong> {{ result.result.duplicate_count }}</p>
      <p><strong>Errors:</strong> {{ result.result.error_count }}</p>
      <p><strong>Accounts:</strong> {{ formatAccounts(result.result.accounts) }}</p>
      <p><strong>Touched Dates:</strong> {{ result.result.touched_trade_dates.join(', ') }}</p>
    </div>

    <div class="card">
      <div class="section-title">Sync Job History</div>
      <table class="trade-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Status</th>
            <th>Type</th>
            <th>Accounts</th>
            <th>Raw</th>
            <th>Inserted</th>
            <th>Duplicates</th>
            <th>Errors</th>
            <th>Created At</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="job in jobs" :key="job.id">
            <td>{{ job.id }}</td>
            <td><span :class="['badge', job.status]">{{ job.status }}</span></td>
            <td>{{ job.job_type }}</td>
            <td>{{ job.broker_account_code || formatAccounts(job.metadata?.accounts) }}</td>
            <td>{{ job.raw_count }}</td>
            <td>{{ job.inserted_count }}</td>
            <td>{{ job.duplicate_count }}</td>
            <td>{{ job.error_count }}</td>
            <td>{{ formatDate(job.created_at) }}</td>
          </tr>
          <tr v-if="!jobs.length">
            <td colspan="9" class="empty-row">No sync jobs yet.</td>
          </tr>
        </tbody>
      </table>
      <PaginationControls :count="totalCount" :current-page="page" :page-size="20" @change="loadJobs" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { deleteIBKRAccountData, fetchIBKRConfigStatus, fetchSyncJobs, startIBKRAccountSync } from '../api/syncs'
import { responseCount, responseRows } from '../api/pagination'
import { refreshAccounts } from '../state/accounts'
import { fetchBrokerAccounts } from '../api/common'
import PaginationControls from '../components/PaginationControls.vue'

const loading = ref(false)
const loadingMode = ref('')
const result = ref(null)
const configStatus = ref(null)
const jobs = ref([])
const page = ref(1)
const totalCount = ref(0)
const accountToDelete = ref('')
const brokerAccounts = ref([])
const selectedAccountId = ref('')
const activeAccounts = computed(() => brokerAccounts.value.filter((account) => account.is_active))
const selectedAccount = computed(() => activeAccounts.value.find((account) => String(account.id) === selectedAccountId.value) || null)
const selectedAccountConfigured = computed(() => Boolean(selectedAccount.value?.token_configured && selectedAccount.value?.flex_query_id))
const localCacheExists = computed(() => Boolean(selectedAccount.value?.local_cache_exists))

const accounts = activeAccounts

function formatDate(v) {
  return new Date(v).toLocaleString()
}

function formatAccounts(accounts) {
  return Array.isArray(accounts) && accounts.length ? accounts.join(', ') : '—'
}

async function loadJobs(nextPage = 1) {
  page.value = nextPage
  const res = await fetchSyncJobs({ page: page.value })
  jobs.value = responseRows(res.data)
  totalCount.value = responseCount(res.data, jobs.value)
}

async function loadAccounts() {
  const res = await fetchBrokerAccounts()
  brokerAccounts.value = responseRows(res.data)
  if (!activeAccounts.value.some((account) => String(account.id) === selectedAccountId.value)) {
    selectedAccountId.value = activeAccounts.value[0] ? String(activeAccounts.value[0].id) : ''
  }
}

async function loadConfigStatus() {
  const res = await fetchIBKRConfigStatus()
  configStatus.value = res.data
}

async function runSync(mode = 'real') {
  if (!selectedAccount.value) {
    alert('Select a configured trading account first.')
    return
  }
  if (mode === 'local' && !localCacheExists.value) {
    alert('Local IBKR Flex XML cache is missing. Please run Start Real IBKR Sync once first.')
    return
  }
  loading.value = true
  loadingMode.value = mode
  try {
    const res = await startIBKRAccountSync(selectedAccount.value.id, mode === 'local')
    result.value = res.data
    await refreshAccounts()
    await loadJobs(1)
    await loadAccounts()
    await loadConfigStatus()
  } catch (err) {
    const serverError = err?.response?.data?.error
    const timeoutError = err?.code === 'ECONNABORTED' ? 'Sync request timed out (15 min). Please retry.' : ''
    await loadJobs(1)
    alert(serverError || timeoutError || err?.message || 'Sync failed')
  } finally {
    loading.value = false
    loadingMode.value = ''
  }
}

async function removeAccountData() {
  const account = accountToDelete.value
  if (!account || !window.confirm(`Remove all locally imported data for ${account}? This cannot be undone.`)) return
  loading.value = true
  loadingMode.value = 'delete'
  try {
    const res = await deleteIBKRAccountData(account)
    result.value = null
    accountToDelete.value = ''
    await refreshAccounts()
    await loadJobs(1)
    await loadAccounts()
    alert(`Removed ${res.data.deleted_execution_count} records for ${account}.`)
  } catch (err) {
    alert(err?.response?.data?.error || err?.message || 'Unable to remove account data')
  } finally {
    loading.value = false
    loadingMode.value = ''
  }
}

onMounted(() => {
  loadJobs(1)
  loadAccounts()
  loadConfigStatus()
})
</script>

<style scoped>
.sync-delete-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.sync-delete-row select { min-width: 200px; }
.danger { background: #b91c1c; }
.danger:hover:not(:disabled) { background: #991b1b; }
.sync-account-picker { display: grid; gap: 6px; max-width: 420px; margin-bottom: 8px; }
</style>
