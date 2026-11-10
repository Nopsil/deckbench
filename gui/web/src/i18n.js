// 界面多语言：我们自己写的文字都在 gui/locales/<lang>.json（扁平键）。
// 游戏里的名字（卡牌、角色、遭遇…）不在这里：后端按所选语言从玩家自己的游戏安装里读。
import { ref } from 'vue'
import zhs from '../../locales/zhs.json'
import en from '../../locales/en.json'
import ja from '../../locales/ja.json'
import ko from '../../locales/ko.json'

export const MESSAGES = { zhs, en, ja, ko }
export const LANGS = [
  { id: 'zhs', label: '简体中文', html: 'zh-CN', intl: 'zh-CN' },
  { id: 'en', label: 'English', html: 'en', intl: 'en-US' },
  { id: 'ja', label: '日本語', html: 'ja', intl: 'ja-JP' },
  { id: 'ko', label: '한국어', html: 'ko', intl: 'ko-KR' },
]
export const lang = ref('zhs')

/** 系统/浏览器语言 → 界面语言：中文 → zhs，日语 → ja，韩语 → ko，其他 → en */
export function detectLang(s) {
  s = String(s || '').toLowerCase().replace('_', '-')
  if (!s) return 'en'
  if (s === 'zhs' || s.startsWith('zh')) return 'zhs'
  if (s.startsWith('ja') || s === 'jpn') return 'ja'
  if (s.startsWith('ko') || s === 'kor') return 'ko'
  return 'en'
}

export function has(key) { return Object.prototype.hasOwnProperty.call(MESSAGES[lang.value] || {}, key) || Object.prototype.hasOwnProperty.call(zhs, key) }

/** t('key', { n: 3 }) → 当前语言的文字；缺了回退中文，再缺就显示键名 */
export function t(key, params) {
  const m = MESSAGES[lang.value] || zhs
  let s = m[key]
  if (s === undefined) s = zhs[key]
  if (s === undefined) return key
  if (params) s = s.replace(/\{(\w+)\}/g, (all, k) => (params[k] === undefined || params[k] === null ? all : String(params[k])))
  return s
}
/** 有翻译就翻译（prefix + 值），没有就原样显示：房间/阶段这类以中文做 ID 的值 */
export function tr(prefix, v) { const k = prefix + v; return has(k) ? t(k) : v }
/** 列表连接符：中文/日文用「、」，英文/韩文用「, 」 */
export function joinList(a) { return (a || []).join(t('sep.list')) }
export function intlLocale() { return (LANGS.find((x) => x.id === lang.value) || LANGS[0]).intl }

function applyHtml(l) {
  try { document.documentElement.lang = (LANGS.find((x) => x.id === l) || LANGS[0]).html } catch (e) { /* ignore */ }
}

/** zh-CN / en-US / ja_JP 这类标记收成界面语言 id。空的或认不出的返回 null（不把乱写的值当成 English）。 */
export function canonLang(s) {
  s = String(s ?? '').trim()
  if (!s) return null
  if (Object.prototype.hasOwnProperty.call(MESSAGES, s)) return s
  const d = detectLang(s)
  if (d !== 'en') return d
  const raw = s.toLowerCase().replace(/_/g, '-')
  if (raw === 'en' || raw.startsWith('en-') || raw === 'english') return 'en'
  return null
}

/** 已记住的选择优先。localStorage 盖过后端；没有 localStorage 时再用 settings.json
 * （桌面版每次端口不同，这个来源还在）。两边都没有，就用浏览器语言，最后才是 en。
 * 不用操作系统语言盖过浏览器。 */
export function resolveLang(stored, saved, browser) {
  return canonLang(stored) || canonLang(saved) || canonLang(browser) || 'en'
}

/** 启动时决定语言。选择写在 localStorage（ui.lang）；换语言时也会同步到后端，但不让后端盖过本机已经记住的选择。 */
export async function initLang() {
  let stored = null
  try { stored = localStorage.getItem('ui.lang') } catch (e) { /* ignore */ }
  let saved = null
  if (!canonLang(stored)) {
    try {
      const r = await fetch('/api/settings')
      if (r.ok) {
        const d = await r.json()
        saved = d && d.lang
      }
    } catch (e) { /* ignore */ }
  }
  const browser = (typeof navigator !== 'undefined' && (navigator.language || (navigator.languages || [])[0])) || ''
  const l = resolveLang(stored, saved, browser)
  lang.value = l
  applyHtml(l)
  if (canonLang(stored) && stored !== l) {
    try { localStorage.setItem('ui.lang', l) } catch (e) { /* ignore */ }
  }
  return l
}

export async function setLang(l) {
  if (!MESSAGES[l]) return
  lang.value = l
  applyHtml(l)
  try { localStorage.setItem('ui.lang', l) } catch (e) { /* ignore */ }
  try { await fetch('/api/settings', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ lang: l }) }) } catch (e) { /* ignore */ }
}
