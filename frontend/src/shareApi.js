// 分享页的数据源：只读，请求不带登录信息。
// 不走 api.js 的 request：那边 401 会跳登录页，还会带上「我是谁」的请求头
import { formatDetail, toQuery } from './api.js'
import { createImageSearch } from './imageSearch.js'
import { fileUrl, thumbUrl } from './thumbs.js'

async function shareRequest(url, options) {
  const res = await fetch(url, options)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw Object.assign(new Error(formatDetail(err.detail) || '请求失败'), { status: res.status })
  }
  return res.json()
}

export function createShareSource(token) {
  const base = `/api/share/${encodeURIComponent(token)}`
  const filesBase = `${base}/files`

  return {
    readonly: true,
    params: { token },
    // 由 ShareLayout 在拿到 /info 后填上
    categoryId: null,
    routes: {
      list: 'ShareList',
      detail: 'ShareDetail',
      imageSearch: 'ShareImageSearch',
      imageSearchDetail: 'ShareImageSearchDetail',
    },
    getInfo: () => shareRequest(`${base}/info`),
    getCategories: () => shareRequest(`${base}/categories`),
    getCategoryFields: (cid) => shareRequest(`${base}/categories/${cid}/fields`),
    getLogs: (params) => shareRequest(`${base}/logs?${toQuery(params)}`),
    getLog: (id) => shareRequest(`${base}/logs/${id}`),
    thumbUrl: (filename) => thumbUrl(filename, filesBase),
    fileUrl: (filename) => fileUrl(filename, filesBase),
    imageSearch: createImageSearch((file) => {
      const fd = new FormData()
      fd.append('file', file)
      return shareRequest(`${base}/search/image?limit=20`, { method: 'POST', body: fd })
    }),
  }
}
