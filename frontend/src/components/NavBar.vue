
<template>
  <nav class="tv-nav journal-nav" aria-label="Primary navigation">
    <router-link class="journal-brand" to="/journal" aria-label="Trade Journal home" @click="closeRecordsMenu">
      <span class="journal-brand-mark">TJ</span>
      <span class="journal-brand-copy">
        <strong>Trade Journal</strong>
        <small>Review · Learn · Improve</small>
      </span>
    </router-link>

    <div class="journal-primary-links">
      <router-link class="journal-nav-link journal-nav-link-primary" to="/journal" @click="closeRecordsMenu">
        <span>Journal</span>
        <small>Plan &amp; review</small>
      </router-link>
      <router-link class="journal-nav-link" to="/" @click="closeRecordsMenu">
        <span>Dashboard</span>
        <small>Performance overview</small>
      </router-link>
      <details ref="recordsMenu" :class="['journal-records-menu', { active: recordsActive }]">
        <summary>
          <span>Records</span>
          <span class="records-chevron" aria-hidden="true">⌄</span>
        </summary>
        <div class="records-popover">
          <router-link to="/trades" @click="closeRecordsMenu">
            <strong>Trade records</strong>
            <small>Grouped trades and details</small>
          </router-link>
          <router-link to="/executions" @click="closeRecordsMenu">
            <strong>Raw executions</strong>
            <small>Audit sync and fills</small>
          </router-link>
        </div>
      </details>
    </div>

    <div class="journal-nav-tools">
      <div v-if="accounts.length" class="global-account-switcher">
        <span class="global-account-label">Account</span>
        <select :value="activeAccountCode" aria-label="Active account" @change="changeAccount">
          <option v-for="account in accounts" :key="account.id" :value="account.account_code">
            {{ account.display_name || account.account_code }}
          </option>
        </select>
      </div>
      <router-link class="settings-link" to="/settings" @click="closeRecordsMenu">Settings</router-link>
    </div>
  </nav>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAccounts } from '../state/accounts'

const { accounts, activeAccountCode, selectActiveAccount } = useAccounts()
const route = useRoute()
const recordsMenu = ref(null)
const recordsActive = computed(() => ['trades', 'trade-detail', 'executions'].includes(route.name))

function changeAccount(event) {
  selectActiveAccount(event.target.value)
}

function closeRecordsMenu() {
  if (recordsMenu.value) recordsMenu.value.open = false
}

watch(() => route.fullPath, closeRecordsMenu)
</script>

<style scoped>
.journal-nav {
  min-height: 76px;
  padding: 10px 28px;
  gap: 28px;
  background:
    radial-gradient(circle at 22% -80%, rgba(66, 133, 255, .32), transparent 42%),
    linear-gradient(135deg, #0b1830 0%, #0d1b34 55%, #101d35 100%);
  box-shadow: 0 8px 28px rgba(15, 23, 42, .14);
}
.journal-brand {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 220px;
  color: #fff;
  text-decoration: none;
}
.journal-brand-mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  background: linear-gradient(135deg, #4d8dff, #2864eb);
  box-shadow: 0 8px 20px rgba(47, 99, 240, .34), inset 0 1px 0 rgba(255, 255, 255, .25);
  font-size: 13px;
  font-weight: 900;
  letter-spacing: -.03em;
}
.journal-brand-copy { display: grid; line-height: 1.1; }
.journal-brand-copy strong { font-size: 17px; letter-spacing: -.02em; }
.journal-brand-copy small { margin-top: 5px; color: rgba(226, 232, 240, .62); font-size: 10px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.journal-primary-links { display: flex; align-items: center; justify-content: center; gap: 6px; flex: 1; }
.journal-nav-link {
  display: grid;
  gap: 2px;
  min-width: 118px;
  padding: 9px 14px;
  border: 1px solid transparent;
  border-radius: 12px;
  color: rgba(241, 245, 249, .78);
  text-decoration: none;
  transition: background .16s ease, border-color .16s ease, color .16s ease, transform .16s ease;
}
.journal-nav-link span { font-size: 14px; font-weight: 800; }
.journal-nav-link small { color: rgba(203, 213, 225, .52); font-size: 10px; white-space: nowrap; }
.journal-nav-link:hover { color: #fff; background: rgba(255, 255, 255, .07); transform: translateY(-1px); }
.journal-nav-link.router-link-exact-active { color: #fff; background: rgba(255, 255, 255, .1); border-color: rgba(255, 255, 255, .12); }
.journal-nav-link-primary.router-link-active {
  color: #fff;
  border-color: rgba(113, 160, 255, .42);
  background: linear-gradient(135deg, rgba(57, 116, 241, .96), rgba(43, 91, 205, .96));
  box-shadow: 0 8px 20px rgba(20, 72, 185, .28);
}
.journal-nav-link-primary.router-link-active small { color: rgba(255, 255, 255, .72); }
.journal-records-menu { position: relative; }
.journal-records-menu summary {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 12px 13px;
  border: 1px solid transparent;
  border-radius: 12px;
  color: rgba(241, 245, 249, .76);
  cursor: pointer;
  font-size: 14px;
  font-weight: 800;
  list-style: none;
  transition: background .16s ease, color .16s ease;
}
.journal-records-menu summary::-webkit-details-marker { display: none; }
.journal-records-menu summary:hover, .journal-records-menu.active summary, .journal-records-menu[open] summary { color: #fff; background: rgba(255, 255, 255, .08); }
.records-chevron { color: rgba(203, 213, 225, .65); font-size: 14px; transition: transform .16s ease; }
.journal-records-menu[open] .records-chevron { transform: rotate(180deg); }
.records-popover {
  position: absolute;
  top: calc(100% + 10px);
  left: 0;
  z-index: 60;
  display: grid;
  gap: 4px;
  width: 230px;
  padding: 8px;
  border: 1px solid #dbe4f1;
  border-radius: 14px;
  background: rgba(255, 255, 255, .98);
  box-shadow: 0 18px 50px rgba(15, 23, 42, .2);
}
.records-popover a { display: grid; gap: 3px; padding: 10px 11px; border-radius: 10px; color: #172033; text-decoration: none; }
.records-popover a:hover, .records-popover a.router-link-active { background: #eef4ff; color: #245fd4; }
.records-popover strong { font-size: 13px; }
.records-popover small { color: #7a8699; font-size: 11px; }
.journal-nav-tools { display: flex; align-items: center; gap: 10px; }
.journal-nav-tools .global-account-switcher { min-width: 210px; border-radius: 14px; }
.settings-link {
  padding: 10px 12px;
  border: 1px solid transparent;
  border-radius: 11px;
  color: rgba(241, 245, 249, .74);
  text-decoration: none;
  font-size: 13px;
  font-weight: 800;
}
.settings-link:hover, .settings-link.router-link-active { color: #fff; border-color: rgba(255, 255, 255, .12); background: rgba(255, 255, 255, .08); }
@media (max-width: 1120px) {
  .journal-nav { flex-wrap: wrap; gap: 10px 18px; }
  .journal-brand { min-width: 190px; }
  .journal-primary-links { order: 3; flex-basis: 100%; justify-content: flex-start; }
  .journal-nav-tools { margin-left: auto; }
}
@media (max-width: 680px) {
  .journal-nav { padding: 10px 14px; }
  .journal-brand-copy small { display: none; }
  .journal-nav-tools { width: 100%; margin-left: 0; }
  .journal-nav-tools .global-account-switcher { flex: 1; min-width: 0; }
  .journal-primary-links { overflow-x: auto; justify-content: flex-start; padding-bottom: 2px; }
  .journal-nav-link { min-width: max-content; }
  .journal-nav-link small { display: none; }
  .records-popover { position: fixed; top: auto; left: 14px; right: 14px; width: auto; }
}
</style>
