export const C = {
  bg: '#131315', side: '#18181B', surface: '#1E1E22', surface2: '#25252A', border: '#2E2E34',
  text: '#EDE9E3', muted: '#9C978F', faint: '#6E6A64',
  accent: '#D97757', accentHover: '#E38B6D', accentPress: '#C4664A',
  green: '#8FBF8F', red: '#E06C6C', blue: '#7FA7C9', sand: '#E3B47E', violet: '#B79CE0',
}
export const SERIES = [C.accent, C.blue, C.sand, C.green, C.violet, '#D98FA6', '#7CC4BE', '#C9C27F']

export const themeOverrides = {
  common: {
    primaryColor: C.accent, primaryColorHover: C.accentHover, primaryColorPressed: C.accentPress, primaryColorSuppl: C.accent,
    infoColor: C.blue, successColor: C.green, warningColor: C.sand, errorColor: C.red,
    bodyColor: C.bg, cardColor: C.surface, modalColor: C.surface, popoverColor: '#26262B', tableColor: C.surface,
    inputColor: '#18181B', borderColor: C.border, dividerColor: C.border,
    textColorBase: C.text, textColor1: C.text, textColor2: '#D6D1CA', textColor3: C.muted,
    borderRadius: '10px', borderRadiusSmall: '7px',
    fontFamily: '"Inter", "HarmonyOS Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Noto Sans SC", system-ui, sans-serif',
    fontFamilyMono: '"JetBrains Mono", "Cascadia Mono", Consolas, "Noto Sans Mono CJK SC", monospace',
    fontSize: '14px', fontSizeMedium: '14px', heightMedium: '36px',
  },
  Card: { borderRadius: '14px', color: C.surface, borderColor: C.border, titleFontSizeMedium: '15px' },
  Button: { fontWeight: '600', borderRadiusMedium: '9px' },
  DataTable: { thColor: '#202024', tdColor: C.surface, tdColorHover: '#24242A', borderColor: C.border, thTextColor: C.muted },
  Tag: { borderRadius: '6px' },
  Menu: { itemHeight: '42px' },
}

export function baseChart() {
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: themeOverrides.common.fontFamily, color: C.muted },
    grid: { left: 48, right: 20, top: 30, bottom: 36, containLabel: true },
    tooltip: { backgroundColor: '#26262B', borderColor: C.border, textStyle: { color: C.text }, extraCssText: 'border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.4)' },
  }
}
export const axis = (o = {}) => ({
  axisLine: { lineStyle: { color: C.border } }, axisTick: { show: false },
  axisLabel: { color: C.muted }, splitLine: { lineStyle: { color: '#26262B' } }, ...o,
})
