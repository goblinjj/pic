<template>
  <div>
    <PageHeader title="我的分享" back />

    <p class="mb-4 text-xs text-slate-500">拿到链接的人无需登录即可只读浏览。撤销后链接立即失效。</p>

    <div v-if="loading" class="py-16 text-center text-sm text-slate-400">加载中...</div>
    <EmptyState v-else-if="shares.length === 0" message="还没有分享链接，可在分类管理里创建" />

    <div v-else class="space-y-3">
      <div
        v-for="s in shares"
        :key="s.token"
        class="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm"
      >
        <div class="mb-2 flex items-center justify-between gap-2">
          <div class="min-w-0">
            <p class="truncate text-sm font-medium text-slate-900">{{ scopeLabel(s) }}</p>
            <p class="text-[11px] text-slate-400">创建于 {{ formatDate(s.created_at) }}</p>
          </div>
          <button
            @click="revoke(s)"
            class="shrink-0 rounded-lg px-2.5 py-1 text-xs font-medium text-red-500 transition-colors hover:bg-red-50"
          >
            撤销
          </button>
        </div>
        <ShareLinkField :token="s.token" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'
import PageHeader from '../components/PageHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import ShareLinkField from '../components/ShareLinkField.vue'

const shares = ref([])
const loading = ref(true)

function scopeLabel(s) {
  if (s.category_id === null) return '全部内容'
  return s.category_name ? `分类「${s.category_name}」` : '分类（已删除）'
}

// 后端存的是 UTC、不带时区的 "YYYY-MM-DD HH:MM:SS"
function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt.replace(' ', 'T') + 'Z').toLocaleString('zh-CN')
}

async function load() {
  try {
    shares.value = await api.getShares()
  } catch (e) {
    alert(e.message)
  } finally {
    loading.value = false
  }
}

async function revoke(s) {
  if (!confirm(`撤销「${scopeLabel(s)}」的分享？已发出的链接将无法打开。`)) return
  try {
    await api.deleteShare(s.token)
    shares.value = shares.value.filter((x) => x.token !== s.token)
  } catch (e) {
    alert(e.message)
  }
}

onMounted(load)
</script>
