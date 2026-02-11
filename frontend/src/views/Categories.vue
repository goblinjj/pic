<template>
  <div>
    <PageHeader title="分类管理" />

    <!-- Add form -->
    <form
      @submit.prevent="addCategory"
      class="mb-4 flex items-center gap-2 rounded-2xl border border-slate-100 bg-white p-3 shadow-sm"
    >
      <input
        type="text"
        v-model="newName"
        placeholder="新分类名称"
        required
        class="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 transition-colors focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
      />
      <input
        type="text"
        v-model.number="newOrder"
        placeholder="排序"
        class="w-16 rounded-xl border border-slate-200 bg-white px-2.5 py-2 text-center text-sm text-slate-900 shadow-sm placeholder:text-slate-400 transition-colors focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
      />
      <button
        type="submit"
        class="shrink-0 rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-primary-700"
      >
        添加
      </button>
    </form>

    <!-- Empty state -->
    <EmptyState v-if="categories.length === 0" message="暂无分类，请先创建" />

    <!-- Category list -->
    <div v-else class="overflow-hidden rounded-2xl border border-slate-100 bg-white shadow-sm divide-y divide-slate-100">
      <div v-for="c in categories" :key="c.id" class="px-5 py-3.5">
        <!-- Edit mode -->
        <form v-if="editing === c.id" @submit.prevent="saveEdit(c.id)" class="flex items-center gap-2">
          <input
            type="text"
            v-model="editName"
            required
            class="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-900 transition-colors focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
          />
          <input
            type="text"
            v-model.number="editOrder"
            class="w-14 rounded-lg border border-slate-200 px-2 py-1.5 text-center text-sm text-slate-900 transition-colors focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
          />
          <button
            type="submit"
            class="shrink-0 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-primary-700"
          >
            保存
          </button>
          <button
            type="button"
            @click="editing = null"
            class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-500 transition-colors hover:bg-slate-100"
          >
            取消
          </button>
        </form>

        <!-- Display mode -->
        <div v-else class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-50 text-xs font-bold text-primary-600">
              {{ c.sort_order }}
            </span>
            <span class="text-sm font-medium text-slate-900">{{ c.name }}</span>
          </div>
          <div class="flex items-center gap-1">
            <button
              @click="startEdit(c)"
              class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
            >
              <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" />
              </svg>
            </button>
            <button
              @click="removeCategory(c.id)"
              class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-red-50 hover:text-red-500"
            >
              <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'
import PageHeader from '../components/PageHeader.vue'
import EmptyState from '../components/EmptyState.vue'

const categories = ref([])
const newName = ref('')
const newOrder = ref(0)
const editing = ref(null)
const editName = ref('')
const editOrder = ref(0)

async function load() {
  categories.value = await api.getCategories()
}

async function addCategory() {
  if (!newName.value.trim()) return
  await api.createCategory({ name: newName.value.trim(), sort_order: newOrder.value || 0 })
  newName.value = ''
  newOrder.value = 0
  await load()
}

function startEdit(c) {
  editing.value = c.id
  editName.value = c.name
  editOrder.value = c.sort_order
}

async function saveEdit(id) {
  await api.updateCategory(id, { name: editName.value.trim(), sort_order: editOrder.value })
  editing.value = null
  await load()
}

async function removeCategory(id) {
  if (!confirm('确定删除此分类？')) return
  try {
    await api.deleteCategory(id)
    await load()
  } catch (e) {
    alert(e.message)
  }
}

onMounted(load)
</script>
