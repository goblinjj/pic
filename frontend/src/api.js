const BASE = ''

// FastAPI 的 422 校验错误里 detail 是一个数组（每项含 loc/msg），
// 直接丢给 new Error 会变成 alert("[object Object]")，得摊平成人看得懂的文字
function formatDetail(detail) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (typeof item === 'string') return item
      const loc = Array.isArray(item?.loc)
        ? item.loc.filter((p) => p !== 'body' && p !== 'query').join('.')
        : ''
      const msg = item?.msg || JSON.stringify(item)
      return loc ? `${loc}: ${msg}` : msg
    })
    return parts.join('；')
  }
  if (detail && typeof detail === 'object') return JSON.stringify(detail)
  return ''
}

async function request(url, options = {}) {
  const res = await fetch(BASE + url, options)
  if (res.status === 204) return null
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(formatDetail(err.detail) || 'Request failed')
  }
  return res.json()
}

export const api = {
  // Categories
  getCategories: () => request('/api/categories'),
  createCategory: (data) => request('/api/categories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }),
  updateCategory: (id, data) => request(`/api/categories/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }),
  deleteCategory: (id) => request(`/api/categories/${id}`, { method: 'DELETE' }),

  // Category fields
  getCategoryFields: (cid) => request(`/api/categories/${cid}/fields`),
  createField: (cid, data) => request(`/api/categories/${cid}/fields`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }),
  updateField: (fid, data) => request(`/api/fields/${fid}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }),
  deleteField: (fid) => request(`/api/fields/${fid}`, { method: 'DELETE' }),
  getFieldUsage: (fid) => request(`/api/fields/${fid}/usage`),

  // Field options
  createOption: (fid, data) => request(`/api/fields/${fid}/options`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }),
  updateOption: (oid, data) => request(`/api/options/${oid}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }),
  deleteOption: (oid) => request(`/api/options/${oid}`, { method: 'DELETE' }),
  getOptionUsage: (oid) => request(`/api/options/${oid}/usage`),

  // Logs
  getLogs: (params = {}) => {
    const q = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v === null || v === undefined || v === '') continue
      if (Array.isArray(v)) {
        for (const item of v) q.append(k, item)
      } else {
        q.set(k, v)
      }
    }
    return request(`/api/logs?${q}`)
  },
  getLog: (id) => request(`/api/logs/${id}`),
  createLog: (formData) => request('/api/logs', {
    method: 'POST',
    body: formData,
  }),
  updateLog: (id, data) => request(`/api/logs/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }),
  updateStatus: (id, status) => request(`/api/logs/${id}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  }),
  deleteLog: (id) => request(`/api/logs/${id}`, { method: 'DELETE' }),

  // Images
  uploadImages: (logId, formData) => request(`/api/logs/${logId}/images`, {
    method: 'POST',
    body: formData,
  }),
  deleteImage: (id) => request(`/api/images/${id}`, { method: 'DELETE' }),
}
