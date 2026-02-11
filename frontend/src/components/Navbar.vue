<template>
  <nav class="navbar">
    <div class="navbar-inner">
      <router-link to="/" class="logo">PicLog</router-link>
      <div class="nav-links">
        <router-link to="/">日志</router-link>
        <router-link to="/categories">分类</router-link>
        <router-link to="/logs/new" class="btn-primary btn-sm">新建日志</router-link>
      </div>
    </div>
  </nav>
</template>

<style scoped>
.navbar {
  background: #fff;
  border-bottom: 1px solid var(--gray-200);
  position: sticky;
  top: 0;
  z-index: 100;
}
.navbar-inner {
  max-width: 960px;
  margin: 0 auto;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.logo {
  font-size: 20px;
  font-weight: 700;
  color: var(--primary);
}
.logo:hover { text-decoration: none; }
.nav-links {
  display: flex;
  align-items: center;
  gap: 16px;
}
.nav-links a { font-size: 14px; color: var(--gray-700); }
.nav-links a:hover { color: var(--primary); text-decoration: none; }
.nav-links a.btn-primary { color: #fff; }
</style>
