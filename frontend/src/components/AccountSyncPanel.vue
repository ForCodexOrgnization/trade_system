<template>
  <section class="card settings-card account-sync-panel">
    <div class="account-sync-heading">
      <div>
        <div class="section-title">IBKR Sync</div>
        <p class="muted-copy">同步目标跟随顶部 Active account。真实同步请求 IBKR；本地测试同步只读取该账户自己的 XML 缓存。</p>
      </div>
      <div class="sync-account-boundary">
        <strong>{{ selectedAccount?.display_name || activeAccountCode || 'No active account' }}</strong>
        <span v-if="selectedAccount">{{ selectedAccount.account_code }} · {{ selectedAccount.connection_status }}</span>
      </div>
    </div>

    <div class="settings-actions sync-actions">
      <button @click="runSync('real')" :disabled="loading || !selectedAccountConfigured">
        {{ loadingMode === 'real' ? 'Syncing from IBKR...' : 'Start Real IBKR Sync' }}
      </button>
      <button class="secondary" @click="runSync('local')" :disabled="loading || !selectedAccount || !localCacheExists">
        {{ loadingMode === 'local' ? 'Syncing from local XML...' : 'Start Local Test Sync' }}
      </button>
    </div>

    <p v-if="selectedAccount && !selectedAccountConfigured" class="muted-copy pnl-negative">
      当前账户尚未配置 Flex Token / Query ID，请先在上方完成配置。
    </p>
    <p :class="['muted-copy', localCacheExists ? 'pnl-positive' : 'pnl-negative']">
      Selected account XML cache: {{ localCacheExists ? 'Ready' : 'Missing — run a real sync for this account first' }}
    </p>

    <div v-if="result" class="sync-result-strip">
      <span><strong>Job:</strong> #{{ result.job_id }}</span>
      <span><strong>Raw:</strong> {{ result.result.raw_count }}</span>
      <span><strong>Inserted:</strong> {{ result.result.inserted_count }}</span>
      <span><strong>Duplicates:</strong> {{ result.result.duplicate_count }}</span>
      <span><strong>Errors:</strong> {{ result.result.error_count }}</span>
    </div>

    <div class="sync-history-header">
      <div class="section-title">Sync Job History</div>
      <span class="muted-copy">可上下或横向滑动查看</span>
    </div>
    <div class="sync-history-scroll" tabindex="0" aria-label="Scrollable sync job history">
      <table class="trade-table sync-history-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Status</th>
            <th>Type</th>
            <th>Account</th>
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
    </div>
    <PaginationControls :count="totalCount" :current-page="page" :page-size="20" @change="loadJobs" />
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import { responseCount, responseRows } from '../api/pagination'
import { fetchSyncJobs, startIBKRAccountSync } from '../api/syncs'
import { refreshAccounts, useAccounts } from '../state/accounts'
import PaginationControls from './PaginationControls.vue'

const loading = ref(false)
const loadingMode = ref('')
const result = ref(null)
const jobs = ref([])
const page = ref(1)
const totalCount = ref(0)
const { accounts, activeAccountCode } = useAccounts()

const selectedAccount = computed(() => accounts.value.find((account) => account.account_code === activeAccountCode.value) || null)
const selectedAccountConfigured = computed(() => Boolean(selectedAccount.value?.token_configured && selectedAccount.value?.flex_query_id))
const localCacheExists = computed(() => Boolean(selectedAccount.value?.local_cache_exists))

function formatDate(value) {
  return new Date(value).toLocaleString()
}

function formatAccounts(accounts) {
  return Array.isArray(accounts) && accounts.length ? accounts.join(', ') : '—'
}

async function loadJobs(nextPage = 1) {
  page.value = nextPage
  const response = await fetchSyncJobs({ page: page.value })
  jobs.value = responseRows(response.data)
  totalCount.value = responseCount(response.data, jobs.value)
}

async function runSync(mode = 'real') {
  if (!selectedAccount.value) {
    alert('Select an active trading account first.')
    return
  }
  if (mode === 'local' && !localCacheExists.value) {
    alert('Local IBKR Flex XML cache is missing. Please run a real sync first.')
    return
  }

  loading.value = true
  loadingMode.value = mode
  try {
    const response = await startIBKRAccountSync(selectedAccount.value.id, mode === 'local')
    result.value = response.data
    await refreshAccounts()
    await loadJobs(1)
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

onMounted(() => {
  loadJobs(1)
})
</script>

<style scoped>
.account-sync-panel { grid-column: 1 / -1; }
.account-sync-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; }
.account-sync-heading .muted-copy { margin: 6px 0 0; }
.sync-account-boundary { display: flex; flex-direction: column; align-items: flex-end; gap: 3px; min-width: 260px; padding: 10px 14px; border: 1px solid var(--line); border-radius: 10px; background: #f8fafc; }
.sync-account-boundary span { color: var(--muted); font-size: 13px; }
.sync-actions { margin-top: 16px; }
.sync-result-strip { display: flex; flex-wrap: wrap; gap: 18px; margin-top: 14px; padding: 12px 14px; border-radius: 10px; background: #ecfdf5; color: #166534; }
.sync-history-header { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-top: 24px; }
.sync-history-scroll { max-height: 360px; margin-top: 10px; overflow: auto; border: 1px solid var(--line); border-radius: 10px; }
.sync-history-table { min-width: 900px; margin: 0; }
.sync-history-table thead { position: sticky; top: 0; z-index: 1; background: #fff; }
@media (max-width: 760px) {
  .account-sync-heading { flex-direction: column; }
  .sync-account-boundary { width: 100%; align-items: flex-start; }
}
</style>
