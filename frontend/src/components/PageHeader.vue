<template>
  <div class="mb-6 flex items-center gap-3">
    <button
      v-if="back"
      @click="$router.back()"
      class="flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
    >
      <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
      </svg>
    </button>
    <h1 class="flex-1 text-xl font-bold text-slate-900">{{ title }}</h1>
    <slot name="actions" />
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  back: { type: Boolean, default: false },
})
</script>
