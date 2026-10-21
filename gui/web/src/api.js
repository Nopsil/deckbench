import { reactive } from 'vue'
import { t, lang, joinList, intlLocale } from './i18n'

async function req(method, url, body, isForm) {
  const opt = { method, headers: { 'x-lang': lang.value } }
  if (body !== undefined) {
    if (isForm) opt.body = body
    else { opt.body = JSON.stringify(body); opt.headers['content-type'] = 'application/json' }
  }
  const r = await fetch(url, opt)
  let data = null
  try { data = await r.json() } catch (e) { /* empty */ }
  if (!r.ok) throw new Error((data && data.detail) || t('api.requestFailed', { status: r.status }))
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
      this.catalog = await api.get('/api/catalog?lang=' + lang.value + (refresh ? '&refresh=1' : ''))
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
  encName(id) {
    if (id === '_unrecorded') return t('room._unrecorded')
    return (this.catalog && this.catalog.encounters && this.catalog.encounters[id]) || id
  },
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
    if (s < 60) return t('fmt.secs', { s })
    const m = Math.floor(s / 60)
    if (m < 60) return t('fmt.minSecs', { m, s: s % 60 })
    return t('fmt.hourMins', { h: Math.floor(m / 60), m: m % 60 })
  },
  time(iso) {
    if (!iso) return '—'
    const d = new Date(iso)
    if (isNaN(d)) return '—'
    return new Intl.DateTimeFormat(intlLocale(), { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(d)
  },
}

export function runTitle(m) {
  if (!m) return ''
  if (m.title) return m.title
  const p = m.params || {}
  if (m.kind === 'batch') {
    let tt = p.game_seed ? t('title.batchSeed', { char: store.charName(p.char), asc: p.asc ?? 0, seed: p.game_seed })
      : t('title.batchN', { char: store.charName(p.char), asc: p.asc ?? 0, n: p.n })
    if (p.force && p.force.length) tt += ` ＋${joinList(p.force.map((x) => store.cardName(x)))}`
    if (p.replace && p.replace.length) tt += ` －${joinList(p.replace.map((x) => store.cardName(x)))}`
    if (p.variants && p.variants.length) tt += ` [${p.variants.join('+')}]`
    return tt
  }
  if (p.preset) {
    const e = store.catalog && store.catalog.experiments.find((x) => x.id === p.preset)
    return t('title.preset', { title: e ? e.title : t('title.presetId', { id: p.preset }), seed: p.seed })
  }
  return t('title.combat', { n: (p.decks || []).length })
}

const STATUS_TYPE = { running: 'warning', done: 'success', failed: 'error', cancelled: 'default', interrupted: 'default', queued: 'info' }
/** STATUS[x].text 每次读取都按当前语言翻译 */
export const STATUS = Object.fromEntries(Object.entries(STATUS_TYPE).map(([k, type]) => [k, { type, get text() { return t('status.' + k) } }]))

for (const k of ['cardName', 'encName', 'charName', 'agentName', 'loadCatalog', 'loadRuns']) store[k] = store[k].bind(store)
