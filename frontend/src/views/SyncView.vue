<template>
  <div>
    <div class="page-header">
      <h1>IBKR Sync</h1>
      <p>全量同步 IBKR executions。真实同步会请求 IBKR 并刷新本地 XML 缓存；本地测试同步只读取缓存，适合反复调试 grouping/dedupe/rebuild。</p>
    </div>

    <div class="card sync-action-card">
      <button @click="runSync('real')" :disabled="loading">
        {{ loadingMode === 'real' ? 'Syncing from IBKR...' : 'Start Real IBKR Sync' }}
      </button>
      <button class="secondary" @click="runSync('local')" :disabled="loading || !localCacheExists">
        {{ loadingMode === 'local' ? 'Syncing from local XML...' : 'Start Local Test Sync' }}
      </button>
      <p class="muted-copy">Local test sync uses backend/data/ibkr_last_flex_statement.xml from the last successful real sync and does not call IBKR.</p>
      <p v-if="configStatus" :class="['muted-copy', localCacheExists ? 'pnl-positive' : 'pnl-negative']">
        Local XML cache: {{ localCacheExists ? 'Ready' : 'Missing — run Start Real IBKR Sync once first' }}
      </p>
    </div>

    <div v-if="result" class="card success-box">
      <div class="section-title">Latest Result</div>
      <p><strong>Job ID:</strong> {{ result.job_id }}</p>
      <p><strong>Raw Count:</strong> {{ result.result.raw_count }}</p>
      <p><strong>Inserted:</strong> {{ result.result.inserted_count }}</p>
      <p><strong>Duplicates:</strong> {{ result.result.duplicate_count }}</p>
      <p><strong>Errors:</strong> {{ result.result.error_count }}</p>
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
            <td>{{ job.raw_count }}</td>
            <td>{{ job.inserted_count }}</td>
            <td>{{ job.duplicate_count }}</td>
            <td>{{ job.error_count }}</td>
            <td>{{ formatDate(job.created_at) }}</td>
          </tr>
          <tr v-if="!jobs.length">
            <td colspan="8" class="empty-row">No sync jobs yet.</td>
          </tr>
        </tbody>
      </table>
      <PaginationControls :count="totalCount" :current-page="page" :page-size="20" @change="loadJobs" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { fetchIBKRConfigStatus, fetchSyncJobs, startIBKRSync, startLocalIBKRSync } from '../api/syncs'
import { responseCount, responseRows } from '../api/pagination'
import PaginationControls from '../components/PaginationControls.vue'

const loading = ref(false)
const loadingMode = ref('')
const result = ref(null)
const configStatus = ref(null)
const jobs = ref([])
const page = ref(1)
const totalCount = ref(0)
const localCacheExists = computed(() => Boolean(configStatus.value?.local_flex_xml_cache_exists))

function formatDate(v) {
  return new Date(v).toLocaleString()
}

async function loadJobs(nextPage = 1) {
  page.value = nextPage
  const res = await fetchSyncJobs({ page: page.value })
  jobs.value = responseRows(res.data)
  totalCount.value = responseCount(res.data, jobs.value)
}

async function loadConfigStatus() {
  const res = await fetchIBKRConfigStatus()
  configStatus.value = res.data
}

async function runSync(mode = 'real') {
  if (mode === 'local' && !localCacheExists.value) {
    alert('Local IBKR Flex XML cache is missing. Please run Start Real IBKR Sync once first.')
    return
  }
  loading.value = true
  loadingMode.value = mode
  try {
    const request = mode === 'local' ? startLocalIBKRSync : startIBKRSync
    const res = await request()
    result.value = res.data
    await loadJobs(1)
    await loadConfigStatus()
  } catch (err) {
    const serverError = err?.response?.data?.error
    const timeoutError = err?.code === 'ECONNABORTED' ? 'Sync request timed out (3 min). Please retry.' : ''
    alert(serverError || timeoutError || err?.message || 'Sync failed')
  } finally {
    loading.value = false
    loadingMode.value = ''
  }
}

onMounted(() => {
  loadJobs(1)
  loadConfigStatus()
})
</script>
