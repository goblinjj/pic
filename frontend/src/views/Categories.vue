<template>
  <div>
    <h1 class="mb-16">分类管理</h1>

    <div class="card">
      <form class="add-form" @submit.prevent="addCategory">
        <input type="text" v-model="newName" placeholder="新分类名称" required />
        <input type="text" v-model.number="newOrder" placeholder="排序" style="width:80px" />
        <button type="submit" class="btn-primary">添加</button>
      </form>
    </div>

    <div class="card" v-if="categories.length === 0" style="text-align:center;color:var(--gray-500)">
      暂无分类，请先创建
    </div>

    <div class="card category-item" v-for="c in categories" :key="c.id">
      <template v-if="editing === c.id">
        <form class="edit-form" @submit.prevent="saveEdit(c.id)">
          <input type="text" v-model="editName" required />
          <input type="text" v-model.number="editOrder" style="width:80px" />
          <button type="submit" class="btn-primary btn-sm">保存</button>
          <button type="button" class="btn-outline btn-sm" @click="editing = null">取消</button>
        </form>
      </template>
      <template v-else>
        <div class="flex items-center justify-between">
          <div>
            <strong>{{ c.name }}</strong>
            <span class="sort-label">排序: {{ c.sort_order }}</span>
          </div>
          <div class="flex gap-8">
            <button class="btn-outline btn-sm" @click="startEdit(c)">编辑</button>
            <button class="btn-danger btn-sm" @click="removeCategory(c.id)">删除</button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'

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

<style scoped>
h1 { font-size: 24px; font-weight: 700; }
.add-form, .edit-form {
  display: flex;
  gap: 8px;
  align-items: center;
}
.add-form input, .edit-form input { flex: 1; }
.category-item { padding: 12px 20px; }
.sort-label { margin-left: 12px; font-size: 13px; color: var(--gray-500); }
</style>
