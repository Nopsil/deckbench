// 历史列表「结果」列。取消、导入、失败但已经打完场次的，显示胜率并标成部分结果。
// 一场都没打完才是破折号。正在跑的仍显示进度。和界面的 run.partial 用同一个词。

export function finishedFights(run) {
  if (!run || typeof run !== 'object') return 0
  const headline = run.headline
  if (!headline || typeof headline !== 'object') return 0
  const raw = run.kind === 'batch' ? headline.n : headline.fights
  if (typeof raw !== 'number' || !Number.isFinite(raw) || raw <= 0) return 0
  return raw
}

/** progress | full | partial | dash */
export function historyResultMode(run) {
  if (!run || typeof run !== 'object') return 'dash'
  if (run.status === 'running') return 'progress'
  if (run.status === 'done') return 'full'
  if (finishedFights(run) > 0) return 'partial'
  return 'dash'
}
