<template>
  <div>
    <div class="page-header detail-header-row">
      <div>
        <h1>Trade Detail</h1>
        <p>成交汇总与原始执行记录。</p>
      </div>
      <button class="secondary" @click="goBack">← Back</button>
    </div>

    <div v-if="loading" class="card">Loading...</div>
    <template v-else-if="trade">
      <div class="card">
          <div class="section-title">Trade Summary</div>
          <table class="kv-table"><tbody>
            <tr><td>Symbol</td><td>{{ trade.symbol }}</td></tr>
            <tr><td>Status</td><td>{{ trade.status }}</td></tr>
            <tr><td>Direction</td><td>{{ trade.direction || '-' }}</td></tr>
            <tr><td>Realized PnL</td><td>{{ fmt(trade.realized_pnl) }}</td></tr>
            <tr><td>Commission</td><td>{{ fmt(trade.commission_total) }}</td></tr>
          </tbody></table>
      </div>

      <div class="card">
        <div class="section-title">Raw Executions</div>
        <table class="trade-table">
          <thead><tr><th>Time</th><th>Side</th><th>Qty</th><th>Price</th></tr></thead>
          <tbody>
            <tr v-for="item in trade.raw_executions" :key="item.id"><td>{{ item.executed_at }}</td><td>{{ item.side }}</td><td>{{ fmt(item.quantity) }}</td><td>{{ fmt(item.price) }}</td></tr>
            <tr v-if="!trade.raw_executions?.length"><td colspan="4" class="empty-row">No executions.</td></tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchTradeGroupDetail } from '../api/trades'
import { formatNumber } from '../utils/formatters'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const trade = ref(null)
const fmt = (v) => formatNumber(v)

async function loadTrade() {
  loading.value = true
  try {
    const res = await fetchTradeGroupDetail(route.params.id)
    trade.value = res.data
  } finally {
    loading.value = false
  }
}

function goBack() { if (window.history.length > 1) router.back(); else router.push('/trades') }
onMounted(loadTrade)
</script>
