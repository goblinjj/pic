<template>
  <div v-if="log">
    <div class="flex items-center justify-between mb-16">
      <h1>#{{ log.id }} {{ log.category_name }}</h1>
      <div class="flex gap-8">
        <router-link :to="`/logs/${log.id}/edit`" class="btn-outline" style="display:inline-block;text-decoration:none">编辑</router-link>
        <button class="btn-danger btn-sm" @click="deleteLog">删除</button>
      </div>
    </div>

    <div class="card">
      <div class="flex items-center justify-between mb-16">
        <span class="badge" :class="log.status === 'completed' ? 'badge-completed' : 'badge-pending'">
          {{ log.status === 'completed' ? '已完成' : '待处理' }}
        </span>
        <button class="btn-outline btn-sm" @click="toggleStatus">
          {{ log.status === 'completed' ? '标记待处理' : '标记完成' }}
        </button>
      </div>

      <div class="detail-row" v-if="log.description">
        <label>描述</label>
        <p>{{ log.description }}</p>
      </div>
      <div class="detail-row" v-if="log.external_link">
        <label>外部链接</label>
        <a :href="log.external_link" target="_blank" rel="noopener">{{ log.external_link }}</a>
      </div>
      <div class="detail-row">
        <label>创建时间</label>
        <span>{{ formatDate(log.created_at) }}</span>
      </div>
      <div class="detail-row">
        <label>更新时间</label>
        <span>{{ formatDate(log.updated_at) }}</span>
      </div>
    </div>

    <div class="card">
      <div class="flex items-center justify-between mb-16">
        <h2>图片 ({{ log.images.length }})</h2>
        <label class="btn-outline btn-sm upload-btn">
          追加上传
          <input type="file" multiple accept="image/*" @change="uploadMore" hidden />
        </label>
      </div>
      <div v-if="log.images.length === 0" style="color:var(--gray-500);font-size:14px">暂无图片</div>
      <div class="image-grid" v-else>
        <div class="image-item" v-for="img in log.images" :key="img.id">
          <img :src="`/uploads/${img.filename}`" :alt="img.original_name" @click="openPreview(img)" />
          <div class="image-actions">
            <span class="image-name">{{ img.original_name }}</span>
            <button class="btn-danger btn-sm" @click="removeImage(img.id)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Image preview modal -->
    <div class="modal-overlay" v-if="previewImg" @click="previewImg = null">
      <img :src="`/uploads/${previewImg.filename}`" class="modal-img" @click.stop />
    </div>
  </div>
  <div v-else class="card" style="text-align:center;color:var(--gray-500)">加载中...</div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api.js'

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
h1 { font-size: 24px; font-weight: 700; }
h2 { font-size: 18px; font-weight: 600; }
.detail-row { margin-bottom: 12px; }
.detail-row label {
  display: block;
  font-size: 12px;
  color: var(--gray-500);
  margin-bottom: 2px;
}
.detail-row p { font-size: 14px; white-space: pre-wrap; }
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}
.image-item {
  border: 1px solid var(--gray-200);
  border-radius: var(--radius);
  overflow: hidden;
}
.image-item > img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  display: block;
  cursor: pointer;
}
.image-actions {
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.image-name {
  font-size: 12px;
  color: var(--gray-500);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 120px;
}
.upload-btn { cursor: pointer; }
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  cursor: pointer;
}
.modal-img {
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  border-radius: 8px;
}
</style>
