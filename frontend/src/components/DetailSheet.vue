<template>
  <!-- 详情子路由的出口：日志卡片以弹层盖在宿主页面（列表、以图搜图结果）上 -->
  <router-view v-slot="{ Component, route }">
    <Transition name="sheet" :duration="250" appear>
      <component :is="Component" :key="route.params.id" />
    </Transition>
  </router-view>
</template>

<style scoped>
/* 遮罩淡入，卡片从底部滑上来；桌面端是居中卡片，轻微上浮 */
.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 0.25s ease;
}
.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}
.sheet-enter-active :deep(.sheet-panel),
.sheet-leave-active :deep(.sheet-panel) {
  transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1);
}
.sheet-enter-from :deep(.sheet-panel),
.sheet-leave-to :deep(.sheet-panel) {
  transform: translateY(100%);
}
@media (min-width: 640px) {
  .sheet-enter-from :deep(.sheet-panel),
  .sheet-leave-to :deep(.sheet-panel) {
    transform: translateY(24px) scale(0.98);
  }
}
</style>
