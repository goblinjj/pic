<template>
  <div>
    <h1 class="mb-16">{{ isEdit ? '编辑日志' : '新建日志' }}</h1>
    <form class="card" @submit.prevent="submit">
      <div class="form-group">
        <label>分类 *</label>
        <select v-model="form.category_id" required>
          <option value="" disabled>请选择分类</option>
          <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
      </div>
      <div class="form-group">
        <label>描述</label>
        <textarea v-model="form.description" rows="3" placeholder="日志描述（可选）"></textarea>
      </div>
      <div class="form-group">
        <label>外部链接</label>
        <input type="url" v-model="form.external_link" placeholder="https://..." />
      </div>
      <div class="form-group" v-if="!isEdit">
        <label>上传图片</label>
        <ImageUploader v-model="files" />
      </div>
      <div class="flex gap-8">
        <button type="submit" class="btn-primary" :disabled="submitting">
          {{ submitting ? '提交中...' : (isEdit ? '保存' : '创建') }}
        </button>
        <button type="button" class="btn-outline" @click="$router.back()">取消</button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api.js'
import ImageUploader from '../components/ImageUploader.vue'

const route = useRoute()
const router = useRouter()
const isEdit = computed(() => !!route.params.id)

const categories = ref([])
const files = ref([])
const submitting = ref(false)
const form = ref({
  category_id: '',
  description: '',
  external_link: '',
})

onMounted(async () => {
  categories.value = await api.getCategories()
  if (isEdit.value) {
    const log = await api.getLog(route.params.id)
    form.value.category_id = log.category_id
    form.value.description = log.description
    form.value.external_link = log.external_link
  }
})

async function submit() {
  if (!form.value.category_id) return alert('请选择分类')
  submitting.value = true
  try {
    if (isEdit.value) {
      await api.updateLog(route.params.id, {
        category_id: form.value.category_id,
        description: form.value.description,
        external_link: form.value.external_link,
      })
      router.push(`/logs/${route.params.id}`)
    } else {
      const fd = new FormData()
      fd.append('category_id', form.value.category_id)
      fd.append('description', form.value.description)
      fd.append('external_link', form.value.external_link)
      for (const f of files.value) {
        fd.append('files', f)
      }
      const log = await api.createLog(fd)
      router.push(`/logs/${log.id}`)
    }
  } catch (e) {
    alert(e.message)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
h1 { font-size: 24px; font-weight: 700; }
</style>
