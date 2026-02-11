<template>
  <div class="min-h-screen bg-slate-50">
    <TopBar />
    <main class="mx-auto max-w-2xl px-4 pb-24 pt-6 md:pb-8">
      <router-view />
    </main>
    <BottomNav />
  </div>
</template>

<script setup>
import TopBar from './components/TopBar.vue'
import BottomNav from './components/BottomNav.vue'
</script>
