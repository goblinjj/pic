<template>
  <div class="flex min-h-[80vh] items-center justify-center">
    <form
      @submit.prevent="submit"
      class="w-full max-w-sm space-y-4 rounded-2xl border border-slate-100 bg-white p-6 shadow-sm"
    >
      <h1 class="text-center text-xl font-bold text-primary-600">PicLog</h1>
      <input
        v-model.trim="username"
        placeholder="账号"
        autocomplete="username"
        autocapitalize="none"
        required
        class="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
      />
      <input
        v-model="password"
        type="password"
        placeholder="密码"
        autocomplete="current-password"
        required
        class="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
      />
      <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
      <button
        type="submit"
        :disabled="busy"
        class="w-full rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-primary-700 disabled:opacity-60"
      >
        {{ busy ? '登录中…' : '登录' }}
      </button>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api.js'
import { setUser } from '../auth.js'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

// 只接受站内路径，防止 ?redirect=//evil.com 这类开放跳转
function safeRedirect(value) {
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') ? value : '/'
}

async function submit() {
  error.value = ''
  busy.value = true
  try {
    const me = await api.login(username.value, password.value)
    setUser(me.username)
    router.replace(safeRedirect(route.query.redirect))
  } catch (e) {
    error.value = e.message
    password.value = ''
  } finally {
    busy.value = false
  }
}
</script>
