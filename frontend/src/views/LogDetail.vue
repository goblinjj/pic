<template>
  <!-- 以卡片形式盖在列表上：手机端从底部弹出，桌面端居中。点遮罩、按返回键都能关 -->
  <div
    class="fixed inset-0 z-[55] flex items-end justify-center bg-black/40 sm:items-center sm:p-6"
    @click.self="close"
  >
    <div class="sheet-panel flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-3xl bg-slate-50 shadow-xl sm:max-h-[88vh] sm:rounded-3xl">
      <!-- Header -->
      <div class="shrink-0 border-b border-slate-100 bg-white px-4 pb-2.5 pt-2">
        <div class="mx-auto mb-2 h-1 w-10 rounded-full bg-slate-200 sm:hidden" />
        <div class="flex items-center gap-1.5">
          <h1 class="flex-1 truncate text-lg font-bold text-slate-900">
            {{ log ? `#${log.id} ${log.category_name}` : '日志详情' }}
          </h1>
          <template v-if="log">
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
          </template>
          <button
            @click="close"
            class="flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
          >
            <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Body -->
      <div class="flex-1 overflow-y-auto overscroll-contain p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
        <div v-if="log">
    <!-- Image gallery -->
    <div class="mb-4 rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
      <div class="mb-3 flex items-center justify-between">
        <h2 class="text-sm font-semibold text-slate-900">图片 ({{ log.images.length }})</h2>
        <div class="flex items-center gap-2">
          <CompressToggle v-model="compress" />
          <button type="button" @click="sheet.open()" class="rounded-lg px-2.5 py-1 text-xs font-medium text-primary-600 transition-colors hover:bg-primary-50">
            追加上传
          </button>
          <PhotoSourceSheet ref="sheet" multiple @pick="uploadMore" />
        </div>
      </div>
      <div v-if="log.images.length === 0" class="py-8 text-center text-sm text-slate-400">暂无图片</div>
      <div v-else class="grid grid-cols-3 gap-2">
        <div v-for="img in log.images" :key="img.id" class="group relative">
          <img
            :src="thumbUrl(img.filename)"
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
        <button type="button" @click="sheet.open()" class="flex aspect-square cursor-pointer items-center justify-center rounded-xl border-2 border-dashed border-slate-200 text-slate-300 transition-colors hover:border-primary-300 hover:text-primary-400">
          <svg class="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Metadata card：字段按网格排，短的两三个一行，长文本/多选才占整行 -->
    <div class="overflow-hidden rounded-2xl border border-slate-100 bg-white shadow-sm divide-y divide-slate-100">
      <!-- Status toggle -->
      <div class="flex items-center justify-between px-4 py-2.5">
        <div class="flex items-center gap-2">
          <span class="text-xs font-medium text-slate-400">状态</span>
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

      <!-- Description：正文，不再单独占一行标题 -->
      <p v-if="log.description" class="whitespace-pre-wrap px-4 py-3 text-sm leading-relaxed text-slate-800">{{ log.description }}</p>

      <!-- Custom fields -->
      <dl v-if="log.field_values.length" class="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-3 sm:grid-cols-3">
        <div
          v-for="fv in log.field_values"
          :key="fv.field_id"
          class="min-w-0"
          :class="{ 'col-span-full': isWide(fv) }"
        >
          <dt class="truncate text-[11px] leading-4 text-slate-400">{{ fv.name }}</dt>
          <dd v-if="fv.type === 'multiselect'" class="mt-1 flex flex-wrap gap-1">
            <span
              v-for="label in fv.option_labels"
              :key="label"
              class="rounded-md bg-slate-100 px-1.5 py-0.5 text-xs font-medium text-slate-700"
            >
              {{ label }}
            </span>
          </dd>
          <dd v-else class="mt-0.5 whitespace-pre-wrap break-words text-sm font-medium text-slate-800">{{ displayValue(fv) }}</dd>
        </div>
      </dl>

      <!-- External link：一行，过长截断 -->
      <a
        v-if="log.external_link"
        :href="log.external_link"
        target="_blank"
        rel="noopener"
        class="flex items-center gap-2 px-4 py-2.5 text-sm text-primary-600 transition-colors hover:bg-slate-50"
      >
        <svg class="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
        </svg>
        <span class="min-w-0 flex-1 truncate">{{ log.external_link }}</span>
      </a>

      <!-- Timestamps：一行小字 -->
      <div class="flex flex-wrap gap-x-3 gap-y-0.5 bg-slate-50/60 px-4 py-2 text-[11px] text-slate-400">
        <span>创建于 {{ formatDate(log.created_at) }}</span>
        <span v-if="log.updated_at && log.updated_at !== log.created_at">更新于 {{ formatDate(log.updated_at) }}</span>
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

        <!-- Loading / error state -->
        <div v-else-if="loadError" class="py-24 text-center text-sm text-slate-400">{{ loadError }}</div>
        <div v-else class="flex items-center justify-center py-24 text-sm text-slate-400">
          <svg class="mr-2 h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
          </svg>
          加载中...
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api.js'
import { compressImages } from '../imageCompress.js'
import StatusBadge from '../components/StatusBadge.vue'
import CompressToggle from '../components/CompressToggle.vue'
import PhotoSourceSheet from '../components/PhotoSourceSheet.vue'
import { thumbUrl } from '../thumbs.js'

const route = useRoute()
const router = useRouter()
const log = ref(null)
const previewImg = ref(null)
const compress = ref(true)
const sheet = ref(null)
const loadError = ref('')

async function loadLog() {
  try {
    log.value = await api.getLog(route.params.id)
  } catch (e) {
    loadError.value = e.status === 404 ? '日志不存在或已删除' : e.message
  }
}

// 从列表/搜图结果点进来的就退回去（Android 返回键、微信返回手势走的也是这条路），
// 直接打开链接进来的没有上一页，换成卡片所在的宿主页面
function close() {
  if (window.history.state?.back) router.back()
  else router.replace(route.matched[route.matched.length - 2]?.path || '/')
}

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleString('zh-CN', {
    year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function displayValue(fv) {
  if (fv.type === 'select') return fv.option_labels[0] || ''
  return fv.value
}

// 窄格子放不下的才占整行：多行文本、较长的文字、选项较多的多选
function isWide(fv) {
  if (fv.type === 'textarea') return true
  if (fv.type === 'multiselect') {
    const labels = fv.option_labels || []
    return labels.length > 3 || labels.join('').length > 10
  }
  return String(displayValue(fv) ?? '').length > 12
}

async function toggleStatus() {
  const newStatus = log.value.status === 'completed' ? 'pending' : 'completed'
  log.value = await api.updateStatus(log.value.id, newStatus)
}

async function deleteLog() {
  if (!confirm('确定删除此日志？所有图片将被一起删除。')) return
  await api.deleteLog(log.value.id)
  close()
}

async function uploadMore(files) {
  const fd = new FormData()
  for (const f of compress.value ? await compressImages(files) : files) {
    fd.append('files', f)
  }
  await api.uploadImages(log.value.id, fd)
  await loadLog()
}

async function removeImage(imgId) {
  if (!confirm('确定删除此图片？')) return
  await api.deleteImage(imgId)
  await loadLog()
}

function openPreview(img) {
  previewImg.value = img
}

function onKeydown(e) {
  if (e.key === 'Escape' && !previewImg.value) close()
}

// 卡片打开期间锁住底下列表的滚动，关掉后列表停在原处
onMounted(() => {
  document.documentElement.style.overflow = 'hidden'
  window.addEventListener('keydown', onKeydown)
  loadLog()
})
onUnmounted(() => {
  document.documentElement.style.overflow = ''
  window.removeEventListener('keydown', onKeydown)
})
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
