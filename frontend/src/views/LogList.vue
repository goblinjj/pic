<template>
  <div>
    <!-- Search bar -->
    <div class="relative mb-4">
      <svg class="absolute left-3 top-1/2 h-4.5 w-4.5 -translate-y-1/2 text-slate-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
      </svg>
      <input
        type="text"
        v-model="search"
        @input="debouncedLoad"
        placeholder="搜索日志..."
        class="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-4 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 transition-colors focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
      />
    </div>

    <!-- Filter pills -->
    <div class="mb-4 flex gap-2 overflow-x-auto hide-scrollbar pb-1">
      <!-- Category pills -->
      <button
        @click="filterCategory = ''; page = 1; load()"
        class="shrink-0 rounded-full px-3.5 py-1.5 text-xs font-medium transition-colors"
        :class="filterCategory === '' ? 'bg-primary-600 text-white shadow-sm' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'"
      >
        全部
      </button>
      <button
        v-for="c in categories"
        :key="c.id"
        @click="filterCategory = c.id; page = 1; load()"
        class="shrink-0 rounded-full px-3.5 py-1.5 text-xs font-medium transition-colors"
        :class="filterCategory === c.id ? 'bg-primary-600 text-white shadow-sm' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'"
      >
        {{ c.name }}
      </button>

      <span class="mx-0.5 w-px self-stretch bg-slate-200"></span>

      <!-- Status pills -->
      <button
        @click="filterStatus = ''; page = 1; load()"
        class="shrink-0 rounded-full px-3.5 py-1.5 text-xs font-medium transition-colors"
        :class="filterStatus === '' ? 'bg-slate-900 text-white shadow-sm' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'"
      >
        全部状态
      </button>
      <button
        @click="filterStatus = 'pending'; page = 1; load()"
        class="shrink-0 rounded-full px-3.5 py-1.5 text-xs font-medium transition-colors"
        :class="filterStatus === 'pending' ? 'bg-amber-500 text-white shadow-sm' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'"
      >
        待处理
      </button>
      <button
        @click="filterStatus = 'completed'; page = 1; load()"
        class="shrink-0 rounded-full px-3.5 py-1.5 text-xs font-medium transition-colors"
        :class="filterStatus === 'completed' ? 'bg-emerald-500 text-white shadow-sm' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'"
      >
        已完成
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-16 text-sm text-slate-400">
      <svg class="mr-2 h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
      </svg>
      加载中...
    </div>

    <!-- Empty state -->
    <EmptyState v-else-if="logs.length === 0" message="暂无日志">
      <router-link
        to="/logs/new"
        class="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-primary-700"
      >
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
        </svg>
        新建日志
      </router-link>
    </EmptyState>

    <!-- Log cards -->
    <div v-else class="space-y-3">
      <router-link
        v-for="log in logs"
        :key="log.id"
        :to="`/logs/${log.id}`"
        class="block rounded-2xl border border-slate-100 bg-white p-4 shadow-sm transition-shadow hover:shadow-md"
      >
        <!-- Image strip -->
        <div v-if="log.images.length" class="mb-3 flex gap-1.5 overflow-hidden rounded-xl">
          <img
            v-for="img in log.images.slice(0, 3)"
            :key="img.id"
            :src="`/uploads/${img.filename}`"
            :alt="img.original_name"
            class="h-20 flex-1 rounded-lg object-cover"
          />
          <div
            v-if="log.images.length > 3"
            class="flex h-20 w-14 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-xs font-medium text-slate-500"
          >
            +{{ log.images.length - 3 }}
          </div>
        </div>

        <!-- Tags row -->
        <div class="mb-2 flex items-center gap-2">
          <span class="inline-flex items-center rounded-md bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary-600">
            {{ log.category_name }}
          </span>
          <StatusBadge :status="log.status" />
        </div>

        <!-- Description -->
        <p v-if="log.description" class="mb-2 line-clamp-2 text-sm text-slate-700">
          {{ log.description }}
        </p>

        <!-- Date -->
        <div class="flex items-center gap-3 text-xs text-slate-400">
          <span>{{ formatDate(log.created_at) }}</span>
          <span v-if="log.external_link" class="flex items-center gap-0.5">
            <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
            </svg>
            链接
          </span>
        </div>
      </router-link>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="flex items-center justify-center gap-4 pt-2">
        <button
          :disabled="page <= 1"
          @click="page--; load()"
          class="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-40 disabled:hover:bg-white"
        >
          <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
          </svg>
        </button>
        <span class="text-sm font-medium text-slate-500">{{ page }} / {{ totalPages }}</span>
        <button
          :disabled="page >= totalPages"
          @click="page++; load()"
          class="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-40 disabled:hover:bg-white"
        >
          <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { api } from '../api.js'
import StatusBadge from '../components/StatusBadge.vue'
import EmptyState from '../components/EmptyState.vue'

const logs = ref([])
const categories = ref([])
const search = ref('')
const filterCategory = ref('')
const filterStatus = ref('')
const page = ref(1)
const size = 20
const total = ref(0)
const loading = ref(false)

const totalPages = computed(() => Math.ceil(total.value / size))

let debounceTimer = null
function debouncedLoad() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { page.value = 1; load() }, 300)
}

async function load() {
  loading.value = true
  try {
    const data = await api.getLogs({
      search: search.value,
      category_id: filterCategory.value || undefined,
      status: filterStatus.value || undefined,
      page: page.value,
      size,
    })
    logs.value = data.items
    total.value = data.total
  } catch (e) {
    alert(e.message)
  } finally {
    loading.value = false
  }
}

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleString('zh-CN')
}

onMounted(async () => {
  categories.value = await api.getCategories()
  load()
})
</script>
