<template>
  <div class="min-h-screen bg-slate-50">
    <TopBar v-if="!route.meta.public" />
    <main class="mx-auto max-w-2xl px-4 pb-24 pt-6 md:pb-8">
      <!-- 缓存列表页和搜图结果页：从详情卡片进编辑页再回来，筛选、已加载页数、滚动位置都保留 -->
      <router-view v-slot="{ Component }">
        <keep-alive :include="['LogList', 'ImageSearch']">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
    <BottomNav v-if="!route.meta.public" />
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'
import TopBar from './components/TopBar.vue'
import BottomNav from './components/BottomNav.vue'

const route = useRoute()
</script>
