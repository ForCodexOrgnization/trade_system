App.vue<template>
  <div class="app-shell">
    <NavBar />
    <main class="page-container">
      <div v-if="loading" class="card account-bootstrap-card">Loading trading accounts...</div>
      <div v-else-if="error" class="card account-bootstrap-card account-bootstrap-error">
        <strong>Unable to load trading accounts</strong>
        <div>{{ error }}</div>
        <button @click="retry">Retry</button>
      </div>
      <div v-else-if="!activeAccountCode && !canRenderWithoutAccount" class="card account-bootstrap-card">
        <strong>No active trading account</strong>
        <div>Run an IBKR sync before opening account-scoped pages.</div>
        <router-link to="/sync">Open Sync</router-link>
      </div>
      <router-view v-else :key="`${accountVersion}:${activeAccountCode}`" />
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import NavBar from './components/NavBar.vue'
import { useAccounts } from './state/accounts'

const {
  activeAccountCode,
  accountVersion,
  loading,
  error,
  initializeAccounts,
  refreshAccounts,
} = useAccounts()
const route = useRoute()
const canRenderWithoutAccount = computed(() => ['sync', 'settings'].includes(route.name))

async function retry() {
  try { await refreshAccounts() } catch {}
}

onMounted(async () => {
  try { await initializeAccounts() } catch {}
})
</script>
