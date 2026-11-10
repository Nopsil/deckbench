<template>
  <n-config-provider :theme="darkTheme" :theme-overrides="themeOv" :locale="nLocale.ui" :date-locale="nLocale.date">
    <n-message-provider>
      <n-dialog-provider>
        <div class="shell">
          <aside class="side">
            <div class="brand">
              <div class="logo">
                <svg viewBox="0 0 64 64"><path d="M32 8l7 18h-5v9h7l-9 21-9-21h7v-9h-5z" fill="#1B1B1E"/></svg>
              </div>
              <div>
                <div class="bt">DeckBench</div>
                <div class="bs">{{ t('app.tagline') }}</div>
              </div>
            </div>
            <nav>
              <router-link v-for="it in nav" :key="it.to" :to="it.to" class="nav" :class="{ on: isOn(it) }">
                <n-icon :component="it.icon" size="19" />
                <span>{{ t(it.text) }}</span>
                <span v-if="it.to === '/run' && runningCount" class="badge">{{ runningCount }}</span>
              </router-link>
            </nav>
            <div class="foot">
              <div class="lang">
                <n-icon :component="World" size="16" class="lang-ic" />
                <n-select :value="lang" :options="langOptions" size="small" :consistent-menu-width="false" :aria-label="t('app.language')" @update:value="changeLang" />
              </div>
              <div v-if="store.catalog" class="eng">
                <div class="dot"></div>
                <div>
                  <div class="et">{{ store.catalog.backend.name }}</div>
                  <div class="es">{{ store.catalog.backend.engine }}</div>
                </div>
              </div>
              <div v-else-if="store.catalogError" class="eng err">{{ t('app.backendError', { err: store.catalogError }) }}</div>
              <div v-else class="eng"><n-spin size="small" /> <span class="es">{{ t('app.loadingSim') }}</span></div>
              <button v-if="appVersion" type="button" class="ver" data-testid="about-version" @click="aboutOpen = true">DeckBench v{{ appVersion }}</button>
            </div>
          </aside>
          <main class="main">
            <header class="top page">
              <div>
                <h1>{{ route.meta.key ? t('page.' + route.meta.key + '.title') : '' }}</h1>
                <div class="sub">{{ route.meta.key ? t('page.' + route.meta.key + '.sub') : '' }}</div>
              </div>
              <div id="top-actions"></div>
            </header>
            <router-view v-slot="{ Component }">
              <transition name="fade" mode="out-in">
                <component :is="Component" :key="route.fullPath + '|' + lang" />
              </transition>
            </router-view>
          </main>
          <n-modal v-model:show="aboutOpen" preset="card" :title="t('about.title')" style="width: min(440px, calc(100vw - 32px))" :bordered="false">
            <div data-testid="about-dialog">
              <p class="about-ver">{{ t('about.versionLine', { version: appVersion }) }}</p>
              <p class="about-note">{{ t('about.manual') }}</p>
              <n-button data-testid="check-updates" :loading="updateBusy" :disabled="updateBusy" @click="checkUpdates">{{ t('about.check') }}</n-button>
              <p v-if="updateStatus === 'up_to_date'" class="about-result" data-testid="update-result">{{ t('about.upToDate') }}</p>
              <p v-else-if="updateStatus === 'update_available'" class="about-result" data-testid="update-result">
                {{ t('about.updateAvailable', { version: updateLatest }) }}
                <a :href="updateUrl" target="_blank" rel="noopener noreferrer">{{ t('about.releaseLink') }}</a>
              </p>
              <p v-else-if="updateStatus === 'offline'" class="about-result" data-testid="update-result">{{ t('about.offline') }}</p>
              <p v-else-if="updateStatus === 'rate_limited'" class="about-result" data-testid="update-result">{{ t('about.rateLimit') }}</p>
              <p v-else-if="updateStatus === 'not_published'" class="about-result" data-testid="update-result">{{ t('about.notPublished') }}</p>
              <p v-else-if="updateStatus" class="about-result" data-testid="update-result">{{ t('about.error') }}</p>
            </div>
          </n-modal>
        </div>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { NConfigProvider, NMessageProvider, NDialogProvider, NIcon, NSelect, NSpin, NModal, NButton, darkTheme, zhCN, dateZhCN, enUS, dateEnUS, jaJP, dateJaJP, koKR, dateKoKR } from 'naive-ui'
import { CirclePlus, PlayerPlay, ChartBar, Scale, ArrowsLeftRight, History, World, Puzzle, Folder, Map, ListSearch, ChartDots, Stack2 } from '@vicons/tabler'
import { themeFor } from './theme'
import { store } from './api'
import { t, lang, LANGS, setLang } from './i18n'

const route = useRoute()
const nav = [
  { to: '/new', text: 'nav.new', icon: CirclePlus },
  { to: '/decks', text: 'nav.decks', icon: Stack2 },
  { to: '/run', text: 'nav.run', icon: PlayerPlay },
  { to: '/report', text: 'nav.report', icon: ChartBar },
  { to: '/ab', text: 'nav.ab', icon: Scale },
  { to: '/compare', text: 'nav.compare', icon: ArrowsLeftRight },
  { to: '/history', text: 'nav.history', icon: History },
  { to: '/import', text: 'nav.import', icon: Folder },
  { to: '/preview', text: 'nav.preview', icon: Map },
  { to: '/explain', text: 'nav.explain', icon: ListSearch },
  { to: '/calibrate', text: 'nav.calibrate', icon: ChartDots },
  { to: '/mods', text: 'nav.mods', icon: Puzzle },
]
const NAIVE = { zhs: { ui: zhCN, date: dateZhCN }, en: { ui: enUS, date: dateEnUS }, ja: { ui: jaJP, date: dateJaJP }, ko: { ui: koKR, date: dateKoKR } }
const nLocale = computed(() => NAIVE[lang.value] || NAIVE.zhs)
const themeOv = computed(() => themeFor(lang.value))
const langOptions = LANGS.map((x) => ({ label: x.label, value: x.id }))
async function changeLang(l) {
  if (l === lang.value) return
  await setLang(l)
  store.loadCatalog()   // 卡牌/角色/遭遇名按新语言从你的游戏安装重新读
}
const isOn = (it) => route.path === it.to || route.path.startsWith(it.to + '/')
const runningCount = computed(() => store.runs.filter((r) => r.status === 'running').length)
let timer
const appVersion = ref('')
const aboutOpen = ref(false)
const updateBusy = ref(false)
const updateStatus = ref('')
const updateLatest = ref('')
const updateUrl = ref('')
function releaseHref(url) {
  return typeof url === 'string' && url.startsWith('https://github.com/Nopsil/deckbench/')
    ? url
    : 'https://github.com/Nopsil/deckbench/releases'
}
async function checkUpdates() {
  updateBusy.value = true
  updateStatus.value = ''
  updateLatest.value = ''
  updateUrl.value = ''
  const ctrl = new AbortController()
  const abortTimer = setTimeout(() => ctrl.abort(), 15000)
  try {
    const r = await fetch('/api/updates/check', { method: 'POST', headers: { 'x-lang': lang.value }, signal: ctrl.signal })
    let data = null
    try { data = await r.json() } catch (e) { data = null }
    if (!data || !data.status) {
      updateStatus.value = 'error'
      return
    }
    updateStatus.value = data.status
    updateLatest.value = data.latest || ''
    updateUrl.value = releaseHref(data.html_url)
  } catch (e) {
    updateStatus.value = 'offline'
  } finally {
    clearTimeout(abortTimer)
    updateBusy.value = false
  }
}
onMounted(() => {
  fetch('/api/version').then((r) => r.json()).then((d) => { appVersion.value = d.version || '' }).catch(() => {})
  store.loadCatalog()
  store.loadRuns()
  timer = setInterval(() => store.loadRuns().catch(() => {}), 3000)
  setInterval(() => fetch('/api/ping').catch(() => {}), 5000)
  fetch('/api/ping').catch(() => {})
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.shell { display: flex; min-height: 100vh; background: linear-gradient(to right, #18181B 236px, #26262B 236px, #26262B 237px, #131315 237px); }
.side { position: sticky; top: 0; height: 100vh; width: 236px; flex: none; background: #18181B; border-right: 1px solid #26262B; display: flex; flex-direction: column; padding: 22px 14px 16px; }
.brand { display: flex; align-items: center; gap: 12px; padding: 0 8px 26px; }
.logo { width: 38px; height: 38px; border-radius: 11px; background: linear-gradient(145deg, #E58A68, #C9603F); display: grid; place-items: center; box-shadow: 0 6px 18px rgba(217,119,87,.28); }
.logo svg { width: 24px; height: 24px; }
.bt { font-weight: 700; font-size: 16px; letter-spacing: .02em; }
.bs { font-size: 11.5px; color: #77736C; margin-top: 2px; }
nav { display: flex; flex-direction: column; gap: 3px; flex: 1; min-height: 0; overflow-y: auto; }
.nav { display: flex; align-items: center; gap: 12px; height: 42px; padding: 0 12px; border-radius: 10px; color: #A9A49C; text-decoration: none; font-size: 14px; font-weight: 500; transition: background .15s, color .15s; position: relative; }
.nav:hover { background: #202024; color: #E4DFD8; }
.nav.on { background: rgba(217,119,87,.13); color: #F2A385; }
.nav.on::before { content: ''; position: absolute; left: -14px; top: 10px; bottom: 10px; width: 3px; border-radius: 0 3px 3px 0; background: #D97757; }
.badge { margin-left: auto; min-width: 20px; height: 20px; padding: 0 6px; border-radius: 10px; background: #D97757; color: #1B1B1E; font-size: 12px; font-weight: 700; display: grid; place-items: center; }
.foot { margin-top: auto; }
.lang { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; padding: 0 2px; }
.lang-ic { color: #77736C; flex: none; }
.eng { display: flex; gap: 10px; align-items: flex-start; padding: 12px; border-radius: 12px; background: #1E1E22; border: 1px solid #2A2A2F; }
.ver { margin-top: 10px; padding: 0 4px; font-size: 11px; color: #77736C; letter-spacing: .02em; background: none; border: 0; cursor: pointer; text-align: left; font-family: inherit; }
.ver:hover { color: #E4DFD8; }
.about-ver { font-size: 15px; font-weight: 600; margin: 0 0 8px; }
.about-note { color: #8A857E; font-size: 12.5px; line-height: 1.5; margin: 0 0 14px; }
.about-result { margin: 14px 0 0; font-size: 13.5px; line-height: 1.5; }
.about-result a { color: #F2A385; }
.eng.err { color: #E06C6C; font-size: 12px; max-height: 72px; overflow: hidden; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #8FBF8F; margin-top: 6px; box-shadow: 0 0 0 3px rgba(143,191,143,.15); flex: none; }
.et { font-size: 12.5px; font-weight: 600; }
.es { font-size: 11px; color: #77736C; margin-top: 3px; line-height: 1.45; }
.main { flex: 1; min-width: 0; }
.top { display: flex; align-items: flex-end; justify-content: space-between; padding-top: 30px; padding-bottom: 22px; }
.top h1 { margin: 0; font-size: 26px; font-weight: 700; letter-spacing: .01em; }
.sub { color: #8A857E; font-size: 13.5px; margin-top: 6px; }
</style>
