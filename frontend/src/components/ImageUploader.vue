<template>
  <div class="uploader">
    <div class="preview-grid" v-if="previews.length">
      <div class="preview-item" v-for="(p, i) in previews" :key="i">
        <img :src="p.url" :alt="p.name" />
        <button class="remove-btn" @click="remove(i)" type="button">&times;</button>
        <span class="preview-name">{{ p.name }}</span>
      </div>
    </div>
    <label class="drop-zone" @dragover.prevent @drop.prevent="onDrop">
      <input type="file" multiple accept="image/*" @change="onSelect" ref="fileInput" />
      <span>点击或拖拽上传图片</span>
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

<style scoped>
.drop-zone {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px dashed var(--gray-300);
  border-radius: var(--radius);
  padding: 32px;
  cursor: pointer;
  color: var(--gray-500);
  transition: border-color 0.15s;
}
.drop-zone:hover { border-color: var(--primary); }
.drop-zone input { display: none; }
.preview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
.preview-item {
  position: relative;
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--gray-200);
}
.preview-item img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  display: block;
}
.preview-name {
  display: block;
  padding: 4px 6px;
  font-size: 11px;
  color: var(--gray-500);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.remove-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(0,0,0,0.6);
  color: #fff;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}
</style>
