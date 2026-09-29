<template>
  <router-link
    :to="`/logs/${log.id}`"
    class="mb-3 block break-inside-avoid rounded-2xl border border-slate-100 bg-white p-3 shadow-sm transition-shadow hover:shadow-md"
  >
    <!-- Cover image -->
    <!-- 图片尺寸要等加载完才知道，加载前先给一个 4:3 的占位框撑出高度：
         既有占位图可看，也让懒加载能按真实位置判断是否临近视口 -->
    <div
      v-if="cover"
      class="relative mb-2 overflow-hidden rounded-xl bg-slate-100"
      :class="{ 'aspect-[4/3]': imgState !== 'loaded' }"
    >
      <div
        v-if="imgState !== 'loaded'"
        class="absolute inset-0 flex items-center justify-center text-slate-300"
        :class="{ 'animate-pulse': imgState === 'loading' }"
      >
        <svg v-if="imgState === 'loading'" class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 0 0 1.5-1.5V6a1.5 1.5 0 0 0-1.5-1.5H3.75A1.5 1.5 0 0 0 2.25 6v12a1.5 1.5 0 0 0 1.5 1.5Zm10.5-11.25h.008v.008h-.008V8.25Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z" />
        </svg>
        <span v-else class="text-[10px]">图片加载失败</span>
      </div>
      <img
        v-show="imgState !== 'error'"
        :src="thumbUrl(cover.filename)"
        :alt="cover.original_name"
        loading="lazy"
        decoding="async"
        @load="imgState = 'loaded'"
        @error="imgState = 'error'"
        class="w-full rounded-xl transition-opacity duration-300"
        :class="imgState === 'loaded' ? 'opacity-100' : 'absolute inset-0 h-full object-cover opacity-0'"
      />
      <span
        v-if="log.images.length > 1"
        class="absolute right-1.5 top-1.5 rounded-full bg-black/50 px-1.5 py-0.5 text-[10px] font-medium text-white"
      >
        {{ log.images.length }}张
      </span>
      <slot name="badge" />
    </div>

    <!-- Tags row -->
    <div class="mb-1.5 flex items-center gap-1.5">
      <span class="inline-flex items-center rounded-md bg-primary-50 px-1.5 py-0.5 text-[10px] font-medium text-primary-600">
        {{ log.category_name }}
      </span>
      <StatusBadge :status="log.status" />
    </div>

    <!-- Description -->
    <p v-if="log.description" class="mb-1.5 line-clamp-2 text-xs text-slate-700">
      {{ log.description }}
    </p>

    <!-- Custom fields on card -->
    <div v-if="log.field_values && log.field_values.length" class="mb-1.5 space-y-0.5">
      <div
        v-for="fv in log.field_values"
        :key="fv.field_id"
        class="flex items-baseline gap-1.5 text-[10px] leading-tight"
      >
        <span class="shrink-0 text-slate-400">{{ fv.name }}</span>
        <span class="min-w-0 flex-1 truncate text-slate-600">{{ cardValue(fv) }}</span>
      </div>
    </div>

    <!-- Date -->
    <div class="text-[10px] text-slate-400">
      {{ formatDate(log.created_at) }}
    </div>
  </router-link>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import StatusBadge from './StatusBadge.vue'
import { thumbUrl } from '../thumbs.js'

const props = defineProps({
  log: { type: Object, required: true },
  // 封面图；不传就用日志的第一张图。搜索结果传「匹配到的那张」
  image: { type: Object, default: null },
})

const cover = computed(() => props.image || props.log.images[0] || null)

// loading → loaded / error；换了封面要重新走一遍
const imgState = ref('loading')
watch(() => cover.value?.filename, () => { imgState.value = 'loading' })

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleString('zh-CN')
}

function cardValue(fv) {
  if (fv.type === 'select') {
    return fv.option_labels[0] || ''
  }
  if (fv.type === 'multiselect') {
    const labels = fv.option_labels || []
    if (labels.length <= 2) return labels.join('、')
    return `${labels.slice(0, 2).join('、')} +${labels.length - 2}`
  }
  return fv.value
}
</script>
