
<template>
  <nav class="tv-nav">
    <div class="tv-nav-brand">IBKR Trade Journal</div>
    <div class="tv-nav-right">
      <div v-if="accounts.length" class="global-account-switcher">
        <span class="global-account-label">Active account</span>
        <select :value="activeAccountCode" aria-label="Active account" @change="changeAccount">
          <option v-for="account in accounts" :key="account.id" :value="account.account_code">
            {{ account.display_name || account.account_code }}
          </option>
        </select>
      </div>
      <div class="tv-nav-links">
        <router-link to="/">Dashboard</router-link>
        <router-link to="/trades">Trades</router-link>
        <router-link to="/executions">Executions</router-link>
        <router-link to="/journal">Journal</router-link>
        <router-link to="/settings">Settings</router-link>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { useAccounts } from '../state/accounts'

const { accounts, activeAccountCode, selectActiveAccount } = useAccounts()

function changeAccount(event) {
  selectActiveAccount(event.target.value)
}
</script>
