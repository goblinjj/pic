<template>
  <div>
    <PageHeader :title="isEdit ? '编辑日志' : '新建日志'" back />

    <form
      @submit.prevent="submit"
      class="space-y-5 rounded-2xl border border-slate-100 bg-white p-5 shadow-sm"
    >
      <!-- Category -->
      <div>
        <label class="mb-1.5 block text-sm font-medium text-slate-700">分类</label>
        <select
          v-model="form.category_id"
          required
          class="w-full appearance-none rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm transition-colors focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
        >
          <option value="" disabled>请选择分类</option>
          <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
      </div>

      <!-- Description -->
      <div>
        <label class="mb-1.5 block text-sm font-medium text-slate-700">描述</label>
        <textarea
          v-model="form.description"
          rows="3"
          placeholder="日志描述（可选）"
          class="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 transition-colors focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
        ></textarea>
      </div>

      <!-- External link -->
      <div>
        <label class="mb-1.5 block text-sm font-medium text-slate-700">外部链接</label>
        <div class="relative">
          <svg class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
          </svg>
          <input
            type="url"
            v-model="form.external_link"
            placeholder="https://..."
            class="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-3.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 transition-colors focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
          />
        </div>
      </div>

      <!-- Wire -->
      <div>
        <label class="mb-1.5 block text-sm font-medium text-slate-700">线材</label>
        <input
          type="text"
          v-model="form.wire"
          placeholder="线材信息（可选）"
          class="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 transition-colors focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
        />
      </div>

      <!-- Image upload (only for new logs) -->
      <div v-if="!isEdit">
        <label class="mb-1.5 block text-sm font-medium text-slate-700">图片</label>
        <ImageUploader v-model="files" />
      </div>

      <!-- Actions -->
      <div class="pt-2">
        <button
          type="submit"
          :disabled="submitting"
          class="w-full rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-primary-700 disabled:opacity-50"
        >
          {{ submitting ? '提交中...' : (isEdit ? '保存修改' : '创建日志') }}
        </button>
        <button
          type="button"
          @click="$router.back()"
          class="mt-2 w-full py-2 text-sm font-medium text-slate-500 transition-colors hover:text-slate-700"
        >
          取消
        </button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api.js'
import ImageUploader from '../components/ImageUploader.vue'
import PageHeader from '../components/PageHeader.vue'

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
  wire: '',
})

onMounted(async () => {
  categories.value = await api.getCategories()
  if (isEdit.value) {
    const log = await api.getLog(route.params.id)
    form.value.category_id = log.category_id
    form.value.description = log.description
    form.value.external_link = log.external_link
    form.value.wire = log.wire || ''
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
        wire: form.value.wire,
      })
      router.push(`/logs/${route.params.id}`)
    } else {
      const fd = new FormData()
      fd.append('category_id', form.value.category_id)
      fd.append('description', form.value.description)
      fd.append('external_link', form.value.external_link)
      fd.append('wire', form.value.wire)
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
