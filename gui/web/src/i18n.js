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

/** 启动时决定语言：已保存的选择 > 后端探测的系统语言 > 浏览器语言。
 *  选择保存在后端（data/settings.json），因为桌面版每次启动端口不同，localStorage 不一定留得住；localStorage 只做备份。 */
export async function initLang() {
  let l = null
  try { l = localStorage.getItem('ui.lang') } catch (e) { /* ignore */ }
  try {
    const r = await fetch('/api/settings')
    if (r.ok) {
      const d = await r.json()
      if (d.lang) l = d.lang
      else if (!l) l = d.os_lang ? detectLang(d.os_lang) : null
    }
  } catch (e) { /* ignore */ }
  if (!l) l = detectLang(navigator.language || (navigator.languages || [])[0])
  if (!MESSAGES[l]) l = 'en'
  lang.value = l
  applyHtml(l)
  return l
}

export async function setLang(l) {
  if (!MESSAGES[l]) return
  lang.value = l
  applyHtml(l)
  try { localStorage.setItem('ui.lang', l) } catch (e) { /* ignore */ }
  try { await fetch('/api/settings', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ lang: l }) }) } catch (e) { /* ignore */ }
}
