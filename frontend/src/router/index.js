import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import TradesView from '../views/TradesView.vue'
import TradeDetailView from '../views/TradeDetailView.vue'
import RawExecutionsView from '../views/RawExecutionsView.vue'
import SettingsView from '../views/SettingsView.vue'

const routes = [
  { path: '/', name: 'dashboard', component: DashboardView },
  { path: '/trades', name: 'trades', component: TradesView },
  { path: '/trades/:id', name: 'trade-detail', component: TradeDetailView, props: true },
  { path: '/executions', name: 'executions', component: RawExecutionsView },
  { path: '/daily-review', redirect: '/' },
  { path: '/journal', redirect: '/' },
  { path: '/reports/monthly', redirect: '/' },
  { path: '/sync', redirect: '/settings' },
  { path: '/settings', name: 'settings', component: SettingsView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
