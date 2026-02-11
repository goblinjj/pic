<template>
  <span
    class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
    :class="status === 'completed'
      ? 'bg-emerald-50 text-emerald-700'
      : 'bg-amber-50 text-amber-700'"
  >
    {{ status === 'completed' ? '已完成' : '待处理' }}
  </span>
</template>

<script setup>
defineProps({
  status: { type: String, required: true },
})
</script>
