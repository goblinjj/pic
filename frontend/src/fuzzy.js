// 选项的模糊搜索：忽略大小写、空格和全/半角差异。
// 连续命中（"nik" → "Nike"）排在前面，其次是按顺序出现的字符（"nk" → "Nike"、"优库" → "优衣库"）。

// 选项超过这个数时才显示搜索框，选项少的字段一眼就能看完
export const SEARCH_THRESHOLD = 8

function normalize(text) {
  return String(text).normalize('NFKC').toLowerCase().replace(/\s+/g, '')
}

// 返回匹配得分，越小越靠前；不匹配返回 -1
function score(label, query) {
  const index = label.indexOf(query)
  if (index !== -1) return index
  let pos = 0
  for (const ch of query) {
    pos = label.indexOf(ch, pos)
    if (pos === -1) return -1
    pos += 1
  }
  return 1000 + pos
}

export function filterOptions(options, query) {
  const q = normalize(query)
  if (!q) return options
  return options
    .map((o, i) => ({ o, i, s: score(normalize(o.label), q) }))
    .filter((x) => x.s !== -1)
    .sort((a, b) => a.s - b.s || a.i - b.i)
    .map((x) => x.o)
}
