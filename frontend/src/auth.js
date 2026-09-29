import { ref } from 'vue'

// 当前登录的用户名；null = 未登录。首次导航时向后端问一次，之后靠 401 兜底
export const currentUser = ref(null)
let checked = false

export async function ensureSession() {
  if (checked) return currentUser.value
  try {
    const res = await fetch('/api/auth/me')
    currentUser.value = res.ok ? (await res.json()).username : null
  } catch {
    currentUser.value = null
  }
  checked = true
  return currentUser.value
}

export function setUser(username) {
  currentUser.value = username
  checked = true
}

export async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' }).catch(() => {})
  // 整页跳转而不是 router.push：列表页被 keep-alive 缓存着上一个账号的数据，
  // 必须整个丢掉，下一个人登录后才不会先看到别人的列表
  window.location.assign('/login')
}
