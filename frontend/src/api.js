const BASE = ''

async function request(url, options = {}) {
  const res = await fetch(BASE + url, options)
  if (res.status === 204) return null
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
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

  // Logs
  getLogs: (params = {}) => {
    const q = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== null && v !== undefined && v !== '') q.set(k, v)
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
