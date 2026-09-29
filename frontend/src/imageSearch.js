// 以图搜图的状态放在模块里而不是页面组件里：拍照入口在列表页等其他页面，
// 拍完再跳到结果页；结果页被移走（比如刷新以外的重新挂载）时结果也还在，不用重新识别。
import { reactive } from 'vue'
import { api } from './api.js'
import { shrinkForSearch } from './imageCompress.js'

export const imageSearch = reactive({
  status: 'idle', // idle | loading | done | error
  previewUrl: '',
  items: [],
  indexed: 0,
  pending: 0,
  error: '',
  errorStatus: 0,
})

let lastFile = null
// 连续拍了两张时，只采用最后一次请求的结果
let latest = 0

export async function searchByPhoto(file) {
  lastFile = file
  const token = ++latest
  if (imageSearch.previewUrl) URL.revokeObjectURL(imageSearch.previewUrl)
  Object.assign(imageSearch, {
    status: 'loading',
    previewUrl: URL.createObjectURL(file),
    items: [],
    error: '',
    errorStatus: 0,
  })
  try {
    const small = await shrinkForSearch(file)
    const data = await api.searchByImage(small)
    if (token !== latest) return
    Object.assign(imageSearch, {
      status: 'done',
      items: data.items,
      indexed: data.indexed,
      pending: data.pending,
    })
  } catch (e) {
    if (token !== latest) return
    Object.assign(imageSearch, { status: 'error', error: e.message, errorStatus: e.status || 0 })
  }
}

export function retry() {
  if (lastFile) searchByPhoto(lastFile)
}

// 相似度档位。初值，需用 scripts/eval-search.py 在真实照片上评测后调整
export const SCORE_LEVELS = [
  { min: 0.75, text: '很可能是同一件', cls: 'bg-emerald-500 text-white' },
  { min: 0.5, text: '相似', cls: 'bg-primary-600 text-white' },
  { min: -Infinity, text: '有点像', cls: 'bg-black/50 text-white' },
]

export function scoreLabel(score) {
  return SCORE_LEVELS.find((level) => score >= level.min)
}
