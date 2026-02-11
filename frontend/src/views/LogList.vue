<template>
  <div>
    <div class="flex items-center justify-between mb-16">
      <h1>日志列表</h1>
      <router-link to="/logs/new" class="btn-primary" style="padding:8px 16px;border-radius:var(--radius);color:#fff;font-size:14px">+ 新建</router-link>
    </div>

    <div class="card filters">
      <div class="filter-row">
        <input type="text" v-model="search" placeholder="搜索描述..." @input="debouncedLoad" />
        <select v-model="filterCategory" @change="load">
          <option value="">全部分类</option>
          <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
        <select v-model="filterStatus" @change="load">
          <option value="">全部状态</option>
          <option value="pending">待处理</option>
          <option value="completed">已完成</option>
        </select>
      </div>
    </div>

    <div v-if="loading" class="card" style="text-align:center;color:var(--gray-500)">加载中...</div>

    <div v-else-if="logs.length === 0" class="card" style="text-align:center;color:var(--gray-500)">暂无日志</div>

    <div v-else>
      <div class="card log-card" v-for="log in logs" :key="log.id">
        <div class="log-header">
          <router-link :to="`/logs/${log.id}`" class="log-title">
            #{{ log.id }}
            <span class="log-category">{{ log.category_name }}</span>
          </router-link>
          <span class="badge" :class="log.status === 'completed' ? 'badge-completed' : 'badge-pending'">
            {{ log.status === 'completed' ? '已完成' : '待处理' }}
          </span>
        </div>
        <p v-if="log.description" class="log-desc">{{ log.description }}</p>
        <div class="log-thumbs" v-if="log.images.length">
          <img v-for="img in log.images.slice(0, 4)" :key="img.id"
               :src="`/uploads/${img.filename}`" :alt="img.original_name" />
          <span v-if="log.images.length > 4" class="more-count">+{{ log.images.length - 4 }}</span>
        </div>
        <div class="log-meta">
          <span>{{ formatDate(log.created_at) }}</span>
          <a v-if="log.external_link" :href="log.external_link" target="_blank" rel="noopener">外部链接</a>
        </div>
      </div>

      <div class="pagination" v-if="totalPages > 1">
        <button class="btn-outline btn-sm" :disabled="page <= 1" @click="page--; load()">上一页</button>
        <span>{{ page }} / {{ totalPages }}</span>
        <button class="btn-outline btn-sm" :disabled="page >= totalPages" @click="page++; load()">下一页</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { api } from '../api.js'

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

<style scoped>
h1 { font-size: 24px; font-weight: 700; }
.filter-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.filter-row input, .filter-row select { width: auto; flex: 1; min-width: 140px; }
.log-card { cursor: default; }
.log-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.log-title { font-weight: 600; font-size: 16px; }
.log-title:hover { text-decoration: none; }
.log-category {
  font-weight: 400;
  font-size: 13px;
  color: var(--gray-500);
  margin-left: 8px;
}
.log-desc {
  font-size: 14px;
  color: var(--gray-700);
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.log-thumbs {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}
.log-thumbs img {
  width: 64px;
  height: 64px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid var(--gray-200);
}
.more-count { font-size: 13px; color: var(--gray-500); }
.log-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--gray-500);
}
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 16px;
  font-size: 14px;
}
</style>
