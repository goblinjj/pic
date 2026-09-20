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

      <!-- Custom fields -->
      <DynamicField
        v-for="f in fields"
        :key="f.id"
        :field="f"
        v-model="fieldValues[f.id]"
      />

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
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api.js'
import ImageUploader from '../components/ImageUploader.vue'
import PageHeader from '../components/PageHeader.vue'
import DynamicField from '../components/DynamicField.vue'

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

const fields = ref([])
const fieldValues = ref({})
// 编辑模式下先把已有值暂存在这里，等分类的字段定义拉回来后再套用
let pendingValues = null

function defaultValue(field) {
  return field.type === 'multiselect' ? [] : ''
}

function buildValueMap(fieldList, existing) {
  const map = {}
  for (const f of fieldList) {
    map[f.id] = f.id in existing ? existing[f.id] : defaultValue(f)
  }
  return map
}

function valuesFromLog(log) {
  const map = {}
  for (const fv of log.field_values || []) {
    map[fv.field_id] = fv.value === null || fv.value === undefined
      ? (fv.type === 'multiselect' ? [] : '')
      : fv.value
  }
  return map
}

watch(() => form.value.category_id, async (cid) => {
  if (!cid) {
    fields.value = []
    fieldValues.value = {}
    pendingValues = null
    return
  }
  fields.value = await api.getCategoryFields(cid)
  // 切换分类时清空已填的自定义值，避免跨分类的脏数据
  fieldValues.value = buildValueMap(fields.value, pendingValues || {})
  pendingValues = null
})

onMounted(async () => {
  categories.value = await api.getCategories()
  if (isEdit.value) {
    const log = await api.getLog(route.params.id)
    pendingValues = valuesFromLog(log)
    form.value.description = log.description
    form.value.external_link = log.external_link
    form.value.category_id = log.category_id
  }
})

function collectFieldValues() {
  const out = {}
  for (const f of fields.value) {
    out[String(f.id)] = fieldValues.value[f.id]
  }
  return out
}

function firstMissingRequired() {
  for (const f of fields.value) {
    if (!f.required) continue
    const v = fieldValues.value[f.id]
    const empty = v === '' || v === null || v === undefined || (Array.isArray(v) && v.length === 0)
    if (empty) return f
  }
  return null
}

async function submit() {
  if (!form.value.category_id) return alert('请选择分类')
  const missing = firstMissingRequired()
  if (missing) return alert(`字段「${missing.name}」为必填`)

  submitting.value = true
  try {
    if (isEdit.value) {
      await api.updateLog(route.params.id, {
        category_id: form.value.category_id,
        description: form.value.description,
        external_link: form.value.external_link,
        field_values: collectFieldValues(),
      })
      router.push(`/logs/${route.params.id}`)
    } else {
      const fd = new FormData()
      fd.append('category_id', form.value.category_id)
      fd.append('description', form.value.description)
      fd.append('external_link', form.value.external_link)
      fd.append('field_values', JSON.stringify(collectFieldValues()))
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
