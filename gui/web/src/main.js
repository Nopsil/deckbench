import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
import NewTest from './pages/NewTest.vue'
import Running from './pages/Running.vue'
import Report from './pages/Report.vue'
import AB from './pages/AB.vue'
import History from './pages/History.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/new' },
    { path: '/new', component: NewTest, meta: { title: '新建测试', sub: '配置一次批量模拟，一键运行' } },
    { path: '/run/:id?', component: Running, meta: { title: '运行中', sub: '实时进度与日志' } },
    { path: '/report/:id?', component: Report, meta: { title: '报告', sub: '胜率、层数、死因与完整报告' } },
    { path: '/ab', component: AB, meta: { title: '单卡 A/B', sub: '同种子配对比较两次测试' } },
    { path: '/history', component: History, meta: { title: '历史记录', sub: '以前跑过的每一次测试' } },
  ],
})
function clientLog(level, msg) {
  try { fetch('/api/clientlog', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ level, msg: String(msg) }) }) } catch (e) { /* ignore */ }
}
window.addEventListener('error', (e) => clientLog('error', `${e.message} @ ${e.filename}:${e.lineno}`))
window.addEventListener('unhandledrejection', (e) => clientLog('error', 'unhandledrejection: ' + (e.reason && (e.reason.stack || e.reason.message) || e.reason)))
const app = createApp(App)
app.config.errorHandler = (err, vm, info) => { console.error(err); clientLog('error', `${info}: ${err && (err.stack || err.message)}`) }
app.use(router).mount('#app')
router.isReady().then(() => clientLog('info', 'ui ready ' + navigator.userAgent))
