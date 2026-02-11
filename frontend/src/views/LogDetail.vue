<template>
  <div v-if="log">
    <PageHeader :title="`#${log.id} ${log.category_name}`" back>
      <template #actions>
        <div class="flex items-center gap-1.5">
          <router-link
            :to="`/logs/${log.id}/edit`"
            class="flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
          >
            <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" />
            </svg>
          </router-link>
          <button
            @click="deleteLog"
            class="flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 transition-colors hover:bg-red-50 hover:text-red-500"
          >
            <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
            </svg>
          </button>
        </div>
      </template>
    </PageHeader>

    <!-- Image gallery -->
    <div class="mb-4 rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
      <div class="mb-3 flex items-center justify-between">
        <h2 class="text-sm font-semibold text-slate-900">图片 ({{ log.images.length }})</h2>
        <label class="cursor-pointer rounded-lg px-2.5 py-1 text-xs font-medium text-primary-600 transition-colors hover:bg-primary-50">
          追加上传
          <input type="file" multiple accept="image/*" @change="uploadMore" class="hidden" />
        </label>
      </div>
      <div v-if="log.images.length === 0" class="py-8 text-center text-sm text-slate-400">暂无图片</div>
      <div v-else class="grid grid-cols-3 gap-2">
        <div v-for="img in log.images" :key="img.id" class="group relative">
          <img
            :src="`/uploads/${img.filename}`"
            :alt="img.original_name"
            class="aspect-square w-full cursor-pointer rounded-xl object-cover transition-opacity group-hover:opacity-90"
            @click="openPreview(img)"
          />
          <button
            @click="removeImage(img.id)"
            class="absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-black/50 text-white opacity-0 transition-opacity group-hover:opacity-100"
          >
            <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <!-- Add card -->
        <label class="flex aspect-square cursor-pointer items-center justify-center rounded-xl border-2 border-dashed border-slate-200 text-slate-300 transition-colors hover:border-primary-300 hover:text-primary-400">
          <svg class="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          <input type="file" multiple accept="image/*" @change="uploadMore" class="hidden" />
        </label>
      </div>
    </div>

    <!-- Metadata card -->
    <div class="rounded-2xl border border-slate-100 bg-white shadow-sm divide-y divide-slate-100">
      <!-- Status toggle -->
      <div class="flex items-center justify-between px-5 py-3.5">
        <div class="flex items-center gap-2.5">
          <span class="text-sm font-medium text-slate-700">状态</span>
          <StatusBadge :status="log.status" />
        </div>
        <button
          @click="toggleStatus"
          class="rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
          :class="log.status === 'completed'
            ? 'bg-amber-50 text-amber-600 hover:bg-amber-100'
            : 'bg-emerald-50 text-emerald-600 hover:bg-emerald-100'"
        >
          {{ log.status === 'completed' ? '标记待处理' : '标记完成' }}
        </button>
      </div>

      <!-- Description -->
      <div v-if="log.description" class="px-5 py-3.5">
        <p class="mb-0.5 text-xs font-medium text-slate-400">描述</p>
        <p class="whitespace-pre-wrap text-sm text-slate-700">{{ log.description }}</p>
      </div>

      <!-- External link -->
      <div v-if="log.external_link" class="px-5 py-3.5">
        <p class="mb-0.5 text-xs font-medium text-slate-400">外部链接</p>
        <a
          :href="log.external_link"
          target="_blank"
          rel="noopener"
          class="inline-flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700"
        >
          {{ log.external_link }}
          <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
          </svg>
        </a>
      </div>

      <!-- Timestamps -->
      <div class="flex gap-8 px-5 py-3.5">
        <div>
          <p class="mb-0.5 text-xs font-medium text-slate-400">创建时间</p>
          <p class="text-sm text-slate-600">{{ formatDate(log.created_at) }}</p>
        </div>
        <div>
          <p class="mb-0.5 text-xs font-medium text-slate-400">更新时间</p>
          <p class="text-sm text-slate-600">{{ formatDate(log.updated_at) }}</p>
        </div>
      </div>
    </div>

    <!-- Fullscreen image preview -->
    <Teleport to="body">
      <Transition name="fade">
        <div
          v-if="previewImg"
          class="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm"
          @click="previewImg = null"
        >
          <button
            class="absolute right-4 top-4 flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20"
            @click.stop="previewImg = null"
          >
            <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
          <img
            :src="`/uploads/${previewImg.filename}`"
            class="max-h-[90vh] max-w-[90vw] rounded-lg object-contain"
            @click.stop
          />
        </div>
      </Transition>
    </Teleport>
  </div>

  <!-- Loading state -->
  <div v-else class="flex items-center justify-center py-24 text-sm text-slate-400">
    <svg class="mr-2 h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
    </svg>
    加载中...
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api.js'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'

const route = useRoute()
const router = useRouter()
const log = ref(null)
const previewImg = ref(null)

async function loadLog() {
  log.value = await api.getLog(route.params.id)
}

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleString('zh-CN')
}

async function toggleStatus() {
  const newStatus = log.value.status === 'completed' ? 'pending' : 'completed'
  log.value = await api.updateStatus(log.value.id, newStatus)
}

async function deleteLog() {
  if (!confirm('确定删除此日志？所有图片将被一起删除。')) return
  await api.deleteLog(log.value.id)
  router.push('/')
}

async function uploadMore(e) {
  const fd = new FormData()
  for (const f of e.target.files) {
    fd.append('files', f)
  }
  await api.uploadImages(log.value.id, fd)
  await loadLog()
  e.target.value = ''
}

async function removeImage(imgId) {
  if (!confirm('确定删除此图片？')) return
  await api.deleteImage(imgId)
  await loadLog()
}

function openPreview(img) {
  previewImg.value = img
}

onMounted(loadLog)
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
