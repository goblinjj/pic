<template>
  <div class="min-h-screen bg-slate-50">
    <TopBar />
    <main class="mx-auto max-w-2xl px-4 pb-24 pt-6 md:pb-8">
      <!-- 缓存列表页：从详情进编辑页再回来，列表的筛选、已加载页数都保留 -->
      <router-view v-slot="{ Component }">
        <keep-alive include="LogList">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
    <BottomNav />
  </div>
</template>

<script setup>
import TopBar from './components/TopBar.vue'
import BottomNav from './components/BottomNav.vue'
</script>
