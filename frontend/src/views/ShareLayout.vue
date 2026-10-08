<template>
  <div>
    <div v-if="state === 'loading'" class="flex items-center justify-center py-24 text-sm text-slate-400">
      加载中...
    </div>

    <EmptyState v-else-if="state === 'invalid'" message="分享链接不存在或已失效" />

    <div v-else-if="state === 'error'" class="py-24 text-center text-sm text-slate-500">
      <p>{{ error }}</p>
      <button @click="init" class="mt-3 font-medium text-primary-600">重试</button>
    </div>

    <template v-else>
      <header class="mb-4">
        <h1 class="text-lg font-bold text-slate-900">{{ title }}</h1>
        <p class="text-xs text-slate-400">只读分享</p>
      </header>
      <!-- 同 App.vue：从详情卡片回来时列表和搜图结果的状态都保留 -->
      <router-view v-slot="{ Component }">
        <keep-alive :include="['LogList', 'ImageSearch']">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, provide, ref } from 'vue'
import { useRoute } from 'vue-router'
import EmptyState from '../components/EmptyState.vue'
import { createShareSource } from '../shareApi.js'

// token 只在进入时读一次：站内没有从一个分享跳到另一个分享的入口
const source = createShareSource(useRoute().params.token)
provide('source', source)

const state = ref('loading') // loading | ready | invalid | error
const error = ref('')
const info = ref(null)

const title = computed(() => {
  if (!info.value) return ''
  const { owner, scope, category_name: name } = info.value
  return scope === 'category' ? `${owner} 分享的「${name}」` : `${owner} 分享的全部内容`
})

async function init() {
  state.value = 'loading'
  try {
    info.value = await source.getInfo()
    // 子页面在 ready 之后才挂载，挂载时读到的就是锁定的分类
    source.categoryId = info.value.category_id
    document.title = `${title.value} - PicLog`
    state.value = 'ready'
  } catch (e) {
    if (e.status === 404) {
      state.value = 'invalid'
    } else {
      error.value = e.message
      state.value = 'error'
    }
  }
}

onMounted(init)
</script>
