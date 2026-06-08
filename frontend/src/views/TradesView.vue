<template>
  <div>
    <div class="page-header">
      <h1>Trades</h1>
      <p>按日期、symbol、状态筛选 trade groups。</p>
    </div>

    <div class="card toolbar">
      <input v-model="filters.date" type="date" @click="openDatePicker" @focus="openDatePicker" />
      <input v-model="filters.symbol" type="text" placeholder="Symbol" />
      <select v-model="filters.status">
        <option value="">All Status</option>
        <option value="open">Open</option>
        <option value="partial">Partial</option>
        <option value="closed">Closed</option>
      </select>
      <button @click="loadTrades(1)">Search</button>
      <button class="secondary" @click="resetFilters">Reset</button>
    </div>

    <div class="card">
      <TradeTable :rows="rows" />
      <PaginationControls :count="totalCount" :current-page="page" :page-size="20" @change="loadTrades" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { fetchTradeGroups } from '../api/trades'
import { responseCount, responseRows } from '../api/pagination'
import TradeTable from '../components/TradeTable.vue'
import PaginationControls from '../components/PaginationControls.vue'

const rows = ref([])
const page = ref(1)
const totalCount = ref(0)
const filters = ref({ date: '', symbol: '', status: '' })

async function loadTrades(nextPage = 1) {
  page.value = nextPage
  const params = { page: page.value }
  if (filters.value.date) params.date = filters.value.date
  if (filters.value.symbol) params.symbol = filters.value.symbol
  if (filters.value.status) params.status = filters.value.status
  const res = await fetchTradeGroups(params)
  rows.value = responseRows(res.data)
  totalCount.value = responseCount(res.data, rows.value)
}

function resetFilters() {
  filters.value = { date: '', symbol: '', status: '' }
  loadTrades(1)
}

function openDatePicker(event) {
  const dateInput = event?.target
  if (dateInput && typeof dateInput.showPicker === 'function') dateInput.showPicker()
}

onMounted(() => loadTrades(1))
</script>
