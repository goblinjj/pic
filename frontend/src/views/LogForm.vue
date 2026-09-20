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
          :disabled="submitting || loadError || fieldsLoading || fieldsError"
          class="w-full rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-primary-700 disabled:opacity-50"
        >
          {{ submitting ? '提交中...' : (loadError ? '加载失败' : (fieldsLoading ? '字段加载中...' : (fieldsError ? '字段加载失败' : (isEdit ? '保存修改' : '创建日志')))) }}
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
const fieldsLoading = ref(false)
const fieldsError = ref(false)
// 初始加载（分类列表 / 编辑模式下的日志本身）失败：表单内容不可信，禁止提交
const loadError = ref(false)
// 编辑模式下把拉到的日志整条留着，每次成功拉到字段定义时按它重新推导回填值。
// 不能用「一次性消费」的暂存值：字段请求失败后用户换个分类再换回来时就没得填了，
// 表单会以空值示人，保存时把真实数据全抹掉。
const loadedLog = ref(null)
// 请求序号：避免分类快速切换时，旧请求的响应晚于新请求落地，覆盖新分类的状态
let requestSeq = 0

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

// 区分「回到日志自己的原分类」与「用户主动换成别的分类」
function isOriginalCategory(cid) {
  return !!loadedLog.value && String(cid) === String(loadedLog.value.category_id)
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
  const seq = ++requestSeq
  if (!cid) {
    fields.value = []
    fieldValues.value = {}
    fieldsLoading.value = false
    return
  }
  fieldsLoading.value = true
  fieldsError.value = false
  try {
    const fetched = await api.getCategoryFields(cid)
    if (seq !== requestSeq) return // 已被更新的分类切换取代，丢弃这次的结果
    fields.value = fetched
    // 只有当前分类就是这条日志自己的原分类时才回填已保存的值；
    // 用户主动切到别的分类必须清空已填值，避免跨分类的脏数据。
    // 每次成功都重新推导，所以「失败 → 换分类 → 换回来」也能拿回原值。
    const prefill = isOriginalCategory(cid) ? valuesFromLog(loadedLog.value) : {}
    fieldValues.value = buildValueMap(fields.value, prefill)
    fieldsLoading.value = false
    fieldsError.value = false
  } catch (e) {
    if (seq !== requestSeq) return // 已被取代的请求失败，与当前分类状态无关，忽略
    fields.value = []
    fieldValues.value = {}
    // loadedLog 保持不动：它是日志已保存字段值的唯一副本，
    // 用户重新选中原分类并成功拉到字段后还要靠它回填
    fieldsLoading.value = false
    fieldsError.value = true
    alert(e.message)
  }
})

onMounted(async () => {
  // 分类列表和日志本身都属于「初始加载」：任何一个失败，表单都是空壳，
  // 编辑模式下直接保存会把描述、链接和全部自定义字段值抹成空
  try {
    categories.value = await api.getCategories()
    if (isEdit.value) {
      const log = await api.getLog(route.params.id)
      loadedLog.value = log
      form.value.description = log.description
      form.value.external_link = log.external_link
      form.value.category_id = log.category_id
    }
  } catch (e) {
    loadError.value = true
    alert(e.message)
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
  if (loadError.value) return alert('加载失败，请刷新页面后再试')
  if (!form.value.category_id) return alert('请选择分类')
  if (fieldsLoading.value) return alert('字段加载中，请稍候')
  if (fieldsError.value) return alert('分类字段加载失败，请重新选择该分类后再试')
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
