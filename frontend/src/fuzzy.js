// 选项的模糊搜索：忽略大小写、空格和全/半角差异。
// 连续命中（"nik" → "Nike"）排在前面，其次是按顺序出现的字符（"nk" → "Nike"、"优库" → "优衣库"）。
// 中文还能用拼音全拼或首字母搜（"youyiku" / "yyk" → "优衣库"）。
import { shallowRef } from 'vue'

// 选项超过这个数时才显示搜索框，选项少的字段一眼就能看完
export const SEARCH_THRESHOLD = 8

// 拼音库有几百 KB，只在真正需要搜索时才加载；加载完成前先按原文匹配。
// 用 ref 存放，filterOptions 在 computed 里读取它，库加载完后搜索结果会自动刷新。
const pinyinFn = shallowRef(null)
let pinyinLoading = false

function loadPinyin() {
  if (pinyinLoading) return
  pinyinLoading = true
  import('pinyin-pro')
    .then((m) => { pinyinFn.value = m.pinyin })
    .catch(() => { pinyinLoading = false })
}

function normalize(text) {
  return String(text).normalize('NFKC').toLowerCase().replace(/\s+/g, '')
}

const pinyinCache = new Map()

// 返回 [全拼, 首字母]，不含中文的文字返回 null
function pinyinKeys(label, pinyin) {
  if (!/[一-鿿]/.test(label)) return null
  if (!pinyinCache.has(label)) {
    const opts = { toneType: 'none', type: 'array', nonZh: 'consecutive' }
    const full = pinyin(label, opts).join('')
    const initials = pinyin(label, { ...opts, pattern: 'first' }).join('')
    pinyinCache.set(label, [normalize(full), normalize(initials)])
  }
  return pinyinCache.get(label)
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

function scoreOption(rawLabel, query, pinyin) {
  const label = normalize(rawLabel)
  let best = score(label, query)
  if (best === 0 || !pinyin) return best
  // 拼音只认连续命中：字母串很长，按顺序跳着匹配几乎什么都能命中
  for (const key of pinyinKeys(label, pinyin) || []) {
    const index = key.indexOf(query)
    if (index !== -1 && (best === -1 || 500 + index < best)) best = 500 + index
  }
  return best
}

export function filterOptions(options, query) {
  const q = normalize(query)
  if (!q) return options
  const pinyin = pinyinFn.value
  if (!pinyin && /[a-z]/.test(q)) loadPinyin()
  return options
    .map((o, i) => ({ o, i, s: scoreOption(o.label, q, pinyin) }))
    .filter((x) => x.s !== -1)
    .sort((a, b) => a.s - b.s || a.i - b.i)
    .map((x) => x.o)
}
