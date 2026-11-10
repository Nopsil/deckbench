/** Flatten parsed changelog spans to text. Used by the dismissible panel. */
export function plainSpans(spans) {
  if (!Array.isArray(spans)) return ''
  return spans.map((span) => {
    if (!span || typeof span !== 'object') return ''
    if (span.t === 'text' || span.t === 'code') return span.s || ''
    if (Array.isArray(span.c)) return plainSpans(span.c)
    return ''
  }).join('')
}

export function previewHeadings(blocks, limit = 4) {
  const out = []
  for (const block of blocks || []) {
    if (block && block.kind === 'h' && block.level === 3) {
      const text = plainSpans(block.spans).trim()
      if (text) out.push(text)
      if (out.length >= limit) break
    }
  }
  return out
}
