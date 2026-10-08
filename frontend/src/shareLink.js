export function shareUrl(token) {
  return `${window.location.origin}/s/${token}`
}

// NAS 走 http，非 localhost 下 navigator.clipboard 不可用（只在安全上下文里有），
// 返回 false 时由调用方选中文本让用户手动复制
export async function copyText(text) {
  if (!window.isSecureContext || !navigator.clipboard) return false
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
