<template>
  <nav class="fixed bottom-0 inset-x-0 z-50 border-t border-slate-200/80 bg-white/80 backdrop-blur-lg md:hidden">
    <div class="mx-auto flex h-16 max-w-lg items-center justify-around px-4">
      <!-- Logs tab -->
      <router-link
        to="/"
        class="flex flex-col items-center gap-0.5 rounded-lg px-3 py-1 transition-colors"
        :class="$route.path === '/' ? 'text-primary-600' : 'text-slate-400'"
      >
        <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 6.75h12M8.25 12h12m-12 5.25h12M3.75 6.75h.007v.008H3.75V6.75Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0ZM3.75 12h.007v.008H3.75V12Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm-.375 5.25h.007v.008H3.75v-.008Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z" />
        </svg>
        <span class="text-[10px] font-medium">日志</span>
      </router-link>

      <!-- New log FAB -->
      <router-link
        to="/logs/new"
        class="-mt-5 flex h-12 w-12 items-center justify-center rounded-full bg-primary-600 text-white shadow-lg shadow-primary-600/30 transition-transform hover:scale-105 active:scale-95"
      >
        <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
        </svg>
      </router-link>

      <!-- Categories tab -->
      <router-link
        to="/categories"
        class="flex flex-col items-center gap-0.5 rounded-lg px-3 py-1 transition-colors"
        :class="$route.path === '/categories' ? 'text-primary-600' : 'text-slate-400'"
      >
        <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 0 0 5.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 0 0 9.568 3Z" />
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 6h.008v.008H6V6Z" />
        </svg>
        <span class="text-[10px] font-medium">分类</span>
      </router-link>
    </div>
  </nav>
</template>
