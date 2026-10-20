import { reactive } from 'vue'

async function req(method, url, body, isForm) {
  const opt = { method, headers: {} }
  if (body !== undefined) {
    if (isForm) opt.body = body
    else { opt.body = JSON.stringify(body); opt.headers['content-type'] = 'application/json' }
  }
  const r = await fetch(url, opt)
  let data = null
  try { data = await r.json() } catch (e) { /* empty */ }
  if (!r.ok) throw new Error((data && data.detail) || `请求失败（${r.status}）`)
  return data
}
export const api = {
  get: (u) => req('GET', u),
  post: (u, b) => req('POST', u, b),
  patch: (u, b) => req('PATCH', u, b),
  del: (u) => req('DELETE', u),
  upload: (u, form) => req('POST', u, form, true),
}

export const store = reactive({
  catalog: null,
  catalogError: null,
  runs: [],
  async loadCatalog(refresh = false) {
    try {
      this.catalog = await api.get('/api/catalog' + (refresh ? '?refresh=1' : ''))
      this.catalogError = null
      this._ci = null
    } catch (e) { this.catalogError = e.message }
  },
  async loadRuns() { this.runs = await api.get('/api/runs') },
  cardName(id) {
    if (!id) return ''
    const up = id.endsWith('+')
    const base = up ? id.slice(0, -1) : id
    const c = this.cardIndex[base]
    if (!c) return id
    return up ? (c.up_name || c.name + '+') : c.name
  },
  encName(id) { return (this.catalog && this.catalog.encounters && this.catalog.encounters[id]) || id },
  charName(id) {
    const c = this.catalog && this.catalog.characters.find((x) => x.id === id)
    return c ? c.name : id
  },
  agentName(kind, id) {
    const l = this.catalog && (kind === 'batch' ? this.catalog.agents_batch : this.catalog.agents_combat)
    const a = l && l.find((x) => x.id === id)
    return a ? a.name : id
  },
  get cardIndex() {
    if (!this._ci && this.catalog) {
      this._ci = {}
      for (const c of this.catalog.cards) this._ci[c.id] = c
    }
    return this._ci || {}
  },
  _ci: null,
})

export const fmt = {
  pct: (x, d = 1) => (x === null || x === undefined ? '—' : (100 * x).toFixed(d) + '%'),
  num: (x, d = 2) => (x === null || x === undefined ? '—' : Number(x).toFixed(d)),
  secs(s) {
    if (s === null || s === undefined) return '—'
    s = Math.round(s)
    if (s < 60) return `${s} 秒`
    const m = Math.floor(s / 60)
    if (m < 60) return `${m} 分 ${s % 60} 秒`
    return `${Math.floor(m / 60)} 小时 ${m % 60} 分`
  },
  time(iso) {
    if (!iso) return '—'
    const d = new Date(iso)
    const p = (n) => String(n).padStart(2, '0')
    return `${d.getMonth() + 1}月${d.getDate()}日 ${p(d.getHours())}:${p(d.getMinutes())}`
  },
}

export function runTitle(m) {
  if (!m) return ''
  if (m.title) return m.title
  const p = m.params || {}
  if (m.kind === 'batch') {
    let t = p.game_seed ? `${store.charName(p.char)} A${p.asc ?? 0} 种子 ${p.game_seed}` : `${store.charName(p.char)} A${p.asc ?? 0} × ${p.n}`
    if (p.force && p.force.length) t += ` ＋${p.force.map((x) => store.cardName(x)).join('、')}`
    if (p.replace && p.replace.length) t += ` －${p.replace.map((x) => store.cardName(x)).join('、')}`
    if (p.variants && p.variants.length) t += ` [${p.variants.join('+')}]`
    return t
  }
  if (p.preset) {
    const e = store.catalog && store.catalog.experiments.find((x) => x.id === p.preset)
    return `${e ? e.title : '实验 ' + p.preset}（种子 ${p.seed}）`
  }
  return `战斗实验（${(p.decks || []).length} 个卡组）`
}

export const STATUS = {
  running: { text: '运行中', type: 'warning' },
  done: { text: '已完成', type: 'success' },
  failed: { text: '失败', type: 'error' },
  cancelled: { text: '已取消', type: 'default' },
  interrupted: { text: '已中断', type: 'default' },
  queued: { text: '排队中', type: 'info' },
}

for (const k of ['cardName', 'encName', 'charName', 'agentName', 'loadCatalog', 'loadRuns']) store[k] = store[k].bind(store)
