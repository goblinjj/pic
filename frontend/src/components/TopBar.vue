<template>
  <header class="hidden md:block sticky top-0 z-50 border-b border-slate-200/80 bg-white/80 backdrop-blur-lg">
    <div class="mx-auto flex h-14 max-w-2xl items-center justify-between px-4">
      <router-link to="/" class="text-lg font-bold text-primary-600 hover:text-primary-700 transition-colors">
        PicLog
      </router-link>
      <nav class="flex items-center gap-1">
        <router-link
          to="/"
          class="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
          :class="{ '!bg-primary-50 !text-primary-600': $route.path === '/' }"
        >
          日志
        </router-link>
        <router-link
          to="/categories"
          class="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
          :class="{ '!bg-primary-50 !text-primary-600': $route.path === '/categories' }"
        >
          分类
        </router-link>
        <router-link
          to="/logs/new"
          class="ml-2 inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-3.5 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-primary-700"
        >
          <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          新建
        </router-link>
      </nav>
    </div>
  </header>
</template>
