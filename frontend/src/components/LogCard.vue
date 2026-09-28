<template>
  <router-link
    :to="`/logs/${log.id}`"
    class="mb-3 block break-inside-avoid rounded-2xl border border-slate-100 bg-white p-3 shadow-sm transition-shadow hover:shadow-md"
  >
    <!-- Cover image -->
    <div v-if="cover" class="relative mb-2 overflow-hidden rounded-xl bg-slate-50">
      <img
        :src="`/uploads/thumbs/${cover.filename}`"
        :alt="cover.original_name"
        class="w-full rounded-xl"
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
import { computed } from 'vue'
import StatusBadge from './StatusBadge.vue'

const props = defineProps({
  log: { type: Object, required: true },
  // 封面图；不传就用日志的第一张图。搜索结果传「匹配到的那张」
  image: { type: Object, default: null },
})

const cover = computed(() => props.image || props.log.images[0] || null)

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
