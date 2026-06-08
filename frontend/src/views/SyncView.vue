<template>
  <div>
    <div class="page-header">
      <h1>IBKR Sync</h1>
      <p>全量同步 IBKR executions，并测试去重与幂等逻辑。</p>
    </div>

    <div class="card">
      <button @click="runSync" :disabled="loading">
        {{ loading ? 'Syncing...' : 'Start Full Sync' }}
      </button>
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
            <td>{{ job.raw_count }}</td>
            <td>{{ job.inserted_count }}</td>
            <td>{{ job.duplicate_count }}</td>
            <td>{{ job.error_count }}</td>
            <td>{{ formatDate(job.created_at) }}</td>
          </tr>
          <tr v-if="!jobs.length">
            <td colspan="7" class="empty-row">No sync jobs yet.</td>
          </tr>
        </tbody>
      </table>
      <PaginationControls :count="totalCount" :current-page="page" :page-size="20" @change="loadJobs" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { fetchSyncJobs, startIBKRSync } from '../api/syncs'
import { responseCount, responseRows } from '../api/pagination'
import PaginationControls from '../components/PaginationControls.vue'

const loading = ref(false)
const result = ref(null)
const jobs = ref([])
const page = ref(1)
const totalCount = ref(0)

function formatDate(v) {
  return new Date(v).toLocaleString()
}

async function loadJobs(nextPage = 1) {
  page.value = nextPage
  const res = await fetchSyncJobs({ page: page.value })
  jobs.value = responseRows(res.data)
  totalCount.value = responseCount(res.data, jobs.value)
}

async function runSync() {
  loading.value = true
  try {
    const res = await startIBKRSync()
    result.value = res.data
    await loadJobs(1)
  } catch (err) {
    const serverError = err?.response?.data?.error
    const timeoutError = err?.code === 'ECONNABORTED' ? 'Sync request timed out (3 min). Please retry.' : ''
    alert(serverError || timeoutError || err?.message || 'Sync failed')
  } finally {
    loading.value = false
  }
}

onMounted(() => loadJobs(1))
</script>
