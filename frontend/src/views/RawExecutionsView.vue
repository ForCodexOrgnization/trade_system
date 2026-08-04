<template>
  <div>
    <div class="page-header">
      <h1>Raw Executions</h1>
      <p>查看原始 execution 记录，支持分页和筛选。</p>
    </div>

    <div class="card toolbar raw-toolbar">
      <input v-model="filters.query" type="text" placeholder="Exec ID / Order ID / Symbol" />
      <input v-model="filters.symbol" type="text" placeholder="Symbol" />
      <div class="raw-account-boundary" title="Controlled by the global account switcher">{{ activeAccountCode }}</div>
      <select v-model="filters.side">
        <option value="">All Side</option>
        <option value="BUY">BUY</option>
        <option value="SELL">SELL</option>
      </select>
      <select v-model="filters.sec_type">
        <option value="">All Asset</option>
        <option value="STK">STK</option>
        <option value="FUT">FUT</option>
      </select>
      <input v-model="filters.date_from" type="date" @click="openDatePicker" @focus="openDatePicker" />
      <input v-model="filters.date_to" type="date" @click="openDatePicker" @focus="openDatePicker" />
      <button @click="loadRows(1)">Search</button>
      <button class="secondary" @click="resetFilters">Reset</button>
    </div>

    <div class="card">
      <table class="trade-table">
        <thead>
          <tr>
            <th>Trade Date</th><th>Time</th><th>Exec ID</th><th>Account</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th><th>Commission</th><th>Asset</th><th>Exchange</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td>{{ row.trade_date }}</td><td>{{ row.executed_at }}</td><td>{{ row.execution_id }}</td><td>{{ row.account }}</td><td>{{ row.symbol }}</td><td>{{ row.side }}</td><td>{{ row.quantity }}</td><td>{{ row.price }}</td><td>{{ row.commission }}</td><td>{{ row.sec_type }}</td><td>{{ row.exchange }}</td>
          </tr>
          <tr v-if="!rows.length"><td colspan="11" class="empty-row">No executions found.</td></tr>
        </tbody>
      </table>
      <PaginationControls :count="totalCount" :current-page="page" :page-size="20" @change="loadRows" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { fetchRawExecutions } from '../api/trades'
import { responseCount, responseRows } from '../api/pagination'
import PaginationControls from '../components/PaginationControls.vue'
import { useAccounts } from '../state/accounts'

const rows = ref([])
const page = ref(1)
const totalCount = ref(0)
const { activeAccountCode } = useAccounts()
const filters = ref({ query: '', symbol: '', side: '', sec_type: '', date_from: '', date_to: '' })

async function loadRows(nextPage = 1) {
  page.value = nextPage
  const params = { page: page.value, ...filters.value }
  Object.keys(params).forEach((key) => { if (!params[key]) delete params[key] })
  const res = await fetchRawExecutions(params)
  rows.value = responseRows(res.data)
  totalCount.value = responseCount(res.data, rows.value)
}

function resetFilters() {
  filters.value = { query: '', symbol: '', side: '', sec_type: '', date_from: '', date_to: '' }
  loadRows(1)
}

function openDatePicker(event) {
  const dateInput = event?.target
  if (dateInput && typeof dateInput.showPicker === 'function') dateInput.showPicker()
}

onMounted(() => loadRows(1))
</script>
