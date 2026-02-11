<template>
  <div>
    <div v-if="previews.length" class="mb-3 grid grid-cols-3 gap-2">
      <div v-for="(p, i) in previews" :key="i" class="group relative">
        <img
          :src="p.url"
          :alt="p.name"
          class="aspect-square w-full rounded-xl border border-slate-100 object-cover"
        />
        <button
          type="button"
          @click="remove(i)"
          class="absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-black/50 text-white opacity-0 transition-opacity group-hover:opacity-100"
        >
          <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
    <label
      class="flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed border-slate-200 bg-slate-50/50 px-4 py-8 text-slate-400 transition-colors hover:border-primary-400 hover:text-primary-500"
      @dragover.prevent
      @drop.prevent="onDrop"
    >
      <input type="file" multiple accept="image/*" @change="onSelect" ref="fileInput" class="hidden" />
      <svg class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 16.5V9.75m0 0 3 3m-3-3-3 3M6.75 19.5a4.5 4.5 0 0 1-1.41-8.775 5.25 5.25 0 0 1 10.233-2.33 3 3 0 0 1 3.758 3.848A3.752 3.752 0 0 1 18 19.5H6.75Z" />
      </svg>
      <span class="text-sm font-medium">点击或拖拽上传图片</span>
    </label>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({ modelValue: { type: Array, default: () => [] } })
const emit = defineEmits(['update:modelValue'])

const previews = ref([])
const fileInput = ref(null)

function addFiles(fileList) {
  for (const f of fileList) {
    if (!f.type.startsWith('image/')) continue
    previews.value.push({ file: f, name: f.name, url: URL.createObjectURL(f) })
  }
  emit('update:modelValue', previews.value.map(p => p.file))
}

function onSelect(e) {
  addFiles(e.target.files)
  e.target.value = ''
}

function onDrop(e) {
  addFiles(e.dataTransfer.files)
}

function remove(index) {
  URL.revokeObjectURL(previews.value[index].url)
  previews.value.splice(index, 1)
  emit('update:modelValue', previews.value.map(p => p.file))
}

watch(() => props.modelValue, (val) => {
  if (!val || val.length === 0) {
    previews.value.forEach(p => URL.revokeObjectURL(p.url))
    previews.value = []
  }
}, { deep: true })
</script>
