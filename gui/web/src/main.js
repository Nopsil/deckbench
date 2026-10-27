import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
import { initLang } from './i18n'
import NewTest from './pages/NewTest.vue'
import Running from './pages/Running.vue'
import Report from './pages/Report.vue'
import AB from './pages/AB.vue'
import History from './pages/History.vue'
import ImportRun from './pages/ImportRun.vue'
import ModEditor from './pages/ModEditor.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/new' },
    { path: '/new', component: NewTest, meta: { key: 'new' } },
    { path: '/run/:id?', component: Running, meta: { key: 'run' } },
    { path: '/report/:id?', component: Report, meta: { key: 'report' } },
    { path: '/ab', component: AB, meta: { key: 'ab' } },
    { path: '/history', component: History, meta: { key: 'history' } },
    { path: '/import', component: ImportRun, meta: { key: 'import' } },
    { path: '/mods', component: ModEditor, meta: { key: 'mods' } },
  ],
})
function clientLog(level, msg) {
  try { fetch('/api/clientlog', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ level, msg: String(msg) }) }) } catch (e) { /* ignore */ }
}
window.addEventListener('error', (e) => clientLog('error', `${e.message} @ ${e.filename}:${e.lineno}`))
window.addEventListener('unhandledrejection', (e) => clientLog('error', 'unhandledrejection: ' + (e.reason && (e.reason.stack || e.reason.message) || e.reason)))
const app = createApp(App)
app.config.errorHandler = (err, vm, info) => { console.error(err); clientLog('error', `${info}: ${err && (err.stack || err.message)}`) }
// 先定语言再挂载，避免先闪一下中文
initLang().finally(() => app.use(router).mount('#app'))
router.isReady().then(() => clientLog('info', 'ui ready ' + navigator.userAgent))
