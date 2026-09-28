<template>
  <button
    type="button"
    role="switch"
    :aria-checked="modelValue"
    @click="emit('update:modelValue', !modelValue)"
    class="flex items-center gap-1.5 text-xs text-slate-600"
  >
    <span
      class="relative inline-flex h-4 w-7 shrink-0 rounded-full transition-colors"
      :class="modelValue ? 'bg-primary-600' : 'bg-slate-300'"
    >
      <span
        class="absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-all"
        :class="modelValue ? 'left-3.5' : 'left-0.5'"
      />
    </span>
    压缩图片
  </button>
</template>

<script setup>
defineProps({ modelValue: { type: Boolean, default: true } })
const emit = defineEmits(['update:modelValue'])
</script>
