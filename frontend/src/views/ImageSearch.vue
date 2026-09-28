<template>
  <div>
    <PageHeader title="拍照搜索" back>
      <template #actions>
        <CameraSearchButton v-if="imageSearch.status !== 'idle'" variant="ghost" label="重新拍照" />
      </template>
    </PageHeader>

    <!-- 还没选照片：直接访问或刷新了页面 -->
    <div
      v-if="imageSearch.status === 'idle'"
      class="flex flex-col items-center rounded-2xl border border-dashed border-slate-200 bg-white py-16 text-center"
    >
      <p class="mb-4 text-sm text-slate-500">拍一张照片，找到库里的同一件东西</p>
      <CameraSearchButton variant="primary" label="拍照搜索" />
    </div>

    <template v-else>
      <!-- 查询照片 -->
      <div class="mb-4 flex items-center gap-3 rounded-2xl border border-slate-100 bg-white p-3 shadow-sm">
        <img :src="imageSearch.previewUrl" alt="查询照片" class="h-16 w-16 shrink-0 rounded-xl object-cover" />
        <p class="min-w-0 flex-1 text-sm">
          <span v-if="imageSearch.status === 'loading'" class="text-slate-500">正在识别…（约需几秒）</span>
          <span v-else-if="imageSearch.status === 'done'" class="text-slate-700">
            找到 {{ imageSearch.items.length }} 条相似记录
          </span>
          <span v-else class="text-red-600">搜索失败</span>
        </p>
      </div>

      <div
        v-if="imageSearch.status === 'done' && imageSearch.pending > 0"
        class="mb-4 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-700"
      >
        还有 {{ imageSearch.pending }} 张图片正在建立索引，结果可能不完整
      </div>

      <!-- 加载骨架 -->
      <div v-if="imageSearch.status === 'loading'" class="columns-2 gap-3">
        <div v-for="n in 4" :key="n" class="mb-3 h-48 animate-pulse break-inside-avoid rounded-2xl bg-slate-100" />
      </div>

      <!-- 出错 -->
      <div
        v-else-if="imageSearch.status === 'error'"
        class="rounded-2xl border border-red-100 bg-red-50 p-4 text-center text-sm text-red-600"
      >
        <p>{{ errorMessage }}</p>
        <button
          v-if="imageSearch.errorStatus !== 503"
          @click="retry"
          class="mt-3 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-red-600 shadow-sm transition-colors hover:bg-red-100"
        >
          重试
        </button>
      </div>

      <EmptyState v-else-if="imageSearch.items.length === 0" message="没有找到相似的记录" />

      <!-- 结果 -->
      <div v-else class="columns-2 gap-3">
        <LogCard
          v-for="hit in imageSearch.items"
          :key="hit.log.id"
          :log="hit.log"
          :image="hit.matched_image"
        >
          <template #badge>
            <span
              class="absolute left-1.5 top-1.5 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
              :class="scoreLabel(hit.score).cls"
            >
              {{ scoreLabel(hit.score).text }}
            </span>
          </template>
        </LogCard>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import LogCard from '../components/LogCard.vue'
import CameraSearchButton from '../components/CameraSearchButton.vue'
import { imageSearch, retry, scoreLabel } from '../imageSearch.js'

const errorMessage = computed(() =>
  imageSearch.errorStatus === 503
    ? '以图搜图未启用，请联系管理员放置模型文件'
    : imageSearch.error || '搜索失败',
)
</script>
