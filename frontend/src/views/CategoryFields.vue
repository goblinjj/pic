<template>
  <div>
    <PageHeader :title="categoryName ? `${categoryName} · 字段` : '字段管理'" back />

    <!-- Add field -->
    <form
      @submit.prevent="addField"
      class="mb-4 space-y-2 rounded-2xl border border-slate-100 bg-white p-3 shadow-sm"
    >
      <div class="flex items-center gap-2">
        <input
          type="text"
          v-model="newField.name"
          placeholder="字段名称"
          required
          class="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 transition-colors focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
        />
        <select
          v-model="newField.type"
          class="shrink-0 rounded-xl border border-slate-200 bg-white px-2.5 py-2 text-sm text-slate-900 shadow-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
        >
          <option v-for="t in FIELD_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
        <input
          type="text"
          v-model.number="newField.sort_order"
          placeholder="排序"
          class="w-14 shrink-0 rounded-xl border border-slate-200 bg-white px-2 py-2 text-center text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
        />
      </div>
      <div class="flex items-center gap-4">
        <label class="flex items-center gap-1.5 text-xs text-slate-600">
          <input type="checkbox" v-model="newField.required" class="h-3.5 w-3.5 rounded border-slate-300 text-primary-600 focus:ring-primary-400" />
          必填
        </label>
        <label class="flex items-center gap-1.5 text-xs text-slate-600">
          <input type="checkbox" v-model="newField.show_in_list" class="h-3.5 w-3.5 rounded border-slate-300 text-primary-600 focus:ring-primary-400" />
          显示在列表卡片
        </label>
        <button
          type="submit"
          class="ml-auto shrink-0 rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-primary-700"
        >
          添加字段
        </button>
      </div>
    </form>

    <!-- Too many cards hint -->
    <p
      v-if="shownInListCount > 3"
      class="mb-3 rounded-xl bg-amber-50 px-3.5 py-2 text-xs text-amber-700"
    >
      已有 {{ shownInListCount }} 个字段标记为显示在列表卡片。卡片空间有限，建议不超过 3 个。
    </p>

    <EmptyState v-if="fields.length === 0" message="该分类还没有字段" />

    <!-- Field list -->
    <div v-else class="overflow-hidden rounded-2xl border border-slate-100 bg-white shadow-sm divide-y divide-slate-100">
      <div v-for="f in fields" :key="f.id" class="px-4 py-3">
        <!-- Edit mode -->
        <form v-if="editing === f.id" @submit.prevent="saveEdit(f)" class="space-y-2">
          <div class="flex items-center gap-2">
            <input
              type="text"
              v-model="editForm.name"
              required
              class="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-900 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
            />
            <span
              class="shrink-0 rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs text-slate-400"
              title="字段类型创建后不可修改，需要改请删除后重建"
            >
              {{ typeLabel(f.type) }}
            </span>
            <input
              type="text"
              v-model.number="editForm.sort_order"
              class="w-12 shrink-0 rounded-lg border border-slate-200 px-2 py-1.5 text-center text-sm text-slate-900 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
            />
          </div>
          <div class="flex items-center gap-4">
            <label class="flex items-center gap-1.5 text-xs text-slate-600">
              <input type="checkbox" v-model="editForm.required" class="h-3.5 w-3.5 rounded border-slate-300 text-primary-600 focus:ring-primary-400" />
              必填
            </label>
            <label class="flex items-center gap-1.5 text-xs text-slate-600">
              <input type="checkbox" v-model="editForm.show_in_list" class="h-3.5 w-3.5 rounded border-slate-300 text-primary-600 focus:ring-primary-400" />
              显示在列表卡片
            </label>
            <button type="submit" class="ml-auto shrink-0 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-700">
              保存
            </button>
            <button type="button" @click="editing = null" class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100">
              取消
            </button>
          </div>
        </form>

        <!-- Display mode -->
        <div v-else>
          <div class="flex items-center justify-between">
            <div class="flex min-w-0 items-center gap-2">
              <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-xs font-bold text-primary-600">
                {{ f.sort_order }}
              </span>
              <span class="truncate text-sm font-medium text-slate-900">{{ f.name }}</span>
              <span class="shrink-0 rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                {{ typeLabel(f.type) }}
              </span>
              <span v-if="f.required" class="shrink-0 rounded-md bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-500">
                必填
              </span>
              <span v-if="f.show_in_list" class="shrink-0 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-600">
                列表
              </span>
            </div>
            <div class="flex shrink-0 items-center gap-1">
              <button
                @click="startEdit(f)"
                class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
              >
                <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" />
                </svg>
              </button>
              <button
                @click="removeField(f)"
                class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-red-50 hover:text-red-500"
              >
                <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                </svg>
              </button>
            </div>
          </div>

          <!-- Options for select / multiselect -->
          <div v-if="hasOptions(f)" class="mt-2 pl-9">
            <button
              @click="toggleOptions(f.id)"
              class="text-xs font-medium text-primary-600 hover:text-primary-700"
            >
              {{ expanded === f.id ? '收起选项' : `选项（${f.options.length}）` }}
            </button>

            <div v-if="expanded === f.id" class="mt-2 space-y-1.5">
              <div
                v-for="o in f.options"
                :key="o.id"
                class="flex items-center gap-2 rounded-lg bg-slate-50 px-2.5 py-1.5"
              >
                <template v-if="editingOption === o.id">
                  <input
                    type="text"
                    v-model="optionForm.label"
                    class="min-w-0 flex-1 rounded border border-slate-200 bg-white px-2 py-1 text-xs text-slate-900 focus:border-primary-400 focus:outline-none"
                  />
                  <input
                    type="text"
                    v-model.number="optionForm.sort_order"
                    class="w-10 shrink-0 rounded border border-slate-200 bg-white px-1 py-1 text-center text-xs text-slate-900 focus:border-primary-400 focus:outline-none"
                  />
                  <button @click="saveOption(o)" class="shrink-0 rounded bg-primary-600 px-2 py-1 text-[10px] font-medium text-white hover:bg-primary-700">
                    保存
                  </button>
                  <button @click="editingOption = null" class="shrink-0 px-1 text-[10px] text-slate-500 hover:text-slate-700">
                    取消
                  </button>
                </template>
                <template v-else>
                  <span class="w-6 shrink-0 text-[10px] text-slate-400">{{ o.sort_order }}</span>
                  <span class="min-w-0 flex-1 truncate text-xs text-slate-700">{{ o.label }}</span>
                  <button @click="startEditOption(o)" class="shrink-0 px-1 text-[10px] text-slate-400 hover:text-slate-600">
                    改名
                  </button>
                  <button @click="removeOption(o)" class="shrink-0 px-1 text-[10px] text-slate-400 hover:text-red-500">
                    删除
                  </button>
                </template>
              </div>

              <form @submit.prevent="addOption(f)" class="flex items-center gap-2 pt-0.5">
                <input
                  type="text"
                  v-model="newOption.label"
                  placeholder="新选项名称"
                  required
                  class="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-900 placeholder:text-slate-400 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
                />
                <input
                  type="text"
                  v-model.number="newOption.sort_order"
                  placeholder="序"
                  class="w-10 shrink-0 rounded-lg border border-slate-200 bg-white px-1 py-1.5 text-center text-xs text-slate-900 placeholder:text-slate-400 focus:border-primary-400 focus:outline-none"
                />
                <button type="submit" class="shrink-0 rounded-lg bg-slate-900 px-2.5 py-1.5 text-[10px] font-medium text-white hover:bg-slate-700">
                  添加
                </button>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api.js'
import PageHeader from '../components/PageHeader.vue'
import EmptyState from '../components/EmptyState.vue'

const FIELD_TYPES = [
  { value: 'text', label: '文本' },
  { value: 'textarea', label: '多行文本' },
  { value: 'number', label: '数字' },
  { value: 'date', label: '日期' },
  { value: 'select', label: '下拉' },
  { value: 'multiselect', label: '多选' },
]

const route = useRoute()
const categoryId = Number(route.params.id)

const categoryName = ref('')
const fields = ref([])
const editing = ref(null)
const editForm = ref({ name: '', sort_order: 0, required: false, show_in_list: false })
const newField = ref({ name: '', type: 'text', sort_order: 0, required: false, show_in_list: false })
const expanded = ref(null)
const editingOption = ref(null)
const optionForm = ref({ label: '', sort_order: 0 })
const newOption = ref({ label: '', sort_order: 0 })

const shownInListCount = computed(() => fields.value.filter((f) => f.show_in_list).length)

function typeLabel(value) {
  const hit = FIELD_TYPES.find((t) => t.value === value)
  return hit ? hit.label : value
}

function hasOptions(field) {
  return field.type === 'select' || field.type === 'multiselect'
}

function toggleOptions(fieldId) {
  expanded.value = expanded.value === fieldId ? null : fieldId
  editingOption.value = null
  newOption.value = { label: '', sort_order: 0 }
}

async function addOption(field) {
  if (!newOption.value.label.trim()) return
  try {
    await api.createOption(field.id, {
      label: newOption.value.label.trim(),
      sort_order: newOption.value.sort_order || 0,
    })
    newOption.value = { label: '', sort_order: 0 }
    await load()
  } catch (e) {
    alert(e.message)
  }
}

function startEditOption(option) {
  editingOption.value = option.id
  optionForm.value = { label: option.label, sort_order: option.sort_order }
}

async function saveOption(option) {
  try {
    await api.updateOption(option.id, {
      label: optionForm.value.label.trim(),
      sort_order: optionForm.value.sort_order,
    })
    editingOption.value = null
    await load()
  } catch (e) {
    alert(e.message)
  }
}

async function removeOption(option) {
  try {
    const { log_count } = await api.getOptionUsage(option.id)
    const message = log_count > 0
      ? `选项「${option.label}」已被 ${log_count} 条日志使用，删除会一并清除这些数据。确定删除？`
      : `确定删除选项「${option.label}」？`
    if (!confirm(message)) return
    await api.deleteOption(option.id)
    await load()
  } catch (e) {
    alert(e.message)
  }
}

async function load() {
  fields.value = await api.getCategoryFields(categoryId)
}

async function loadCategoryName() {
  const all = await api.getCategories()
  const hit = all.find((c) => c.id === categoryId)
  categoryName.value = hit ? hit.name : ''
}

async function addField() {
  if (!newField.value.name.trim()) return
  try {
    await api.createField(categoryId, {
      name: newField.value.name.trim(),
      type: newField.value.type,
      sort_order: newField.value.sort_order || 0,
      required: newField.value.required,
      show_in_list: newField.value.show_in_list,
    })
    newField.value = { name: '', type: 'text', sort_order: 0, required: false, show_in_list: false }
    await load()
  } catch (e) {
    alert(e.message)
  }
}

function startEdit(f) {
  editing.value = f.id
  editForm.value = {
    name: f.name,
    sort_order: f.sort_order,
    required: f.required,
    show_in_list: f.show_in_list,
  }
}

async function saveEdit(f) {
  try {
    await api.updateField(f.id, {
      name: editForm.value.name.trim(),
      sort_order: editForm.value.sort_order,
      required: editForm.value.required,
      show_in_list: editForm.value.show_in_list,
    })
    editing.value = null
    await load()
  } catch (e) {
    alert(e.message)
  }
}

async function removeField(f) {
  try {
    const { log_count } = await api.getFieldUsage(f.id)
    const message = log_count > 0
      ? `字段「${f.name}」已被 ${log_count} 条日志使用，删除会一并清除这些数据。确定删除？`
      : `确定删除字段「${f.name}」？`
    if (!confirm(message)) return
    await api.deleteField(f.id)
    await load()
  } catch (e) {
    alert(e.message)
  }
}

onMounted(async () => {
  await loadCategoryName()
  await load()
})
</script>
