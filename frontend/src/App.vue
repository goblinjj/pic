<template>
  <div id="app-root">
    <Navbar />
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import Navbar from './components/Navbar.vue'
</script>

<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --primary: #4f46e5;
  --primary-hover: #4338ca;
  --danger: #ef4444;
  --danger-hover: #dc2626;
  --success: #10b981;
  --gray-50: #f9fafb;
  --gray-100: #f3f4f6;
  --gray-200: #e5e7eb;
  --gray-300: #d1d5db;
  --gray-500: #6b7280;
  --gray-700: #374151;
  --gray-900: #111827;
  --radius: 8px;
  --shadow: 0 1px 3px rgba(0,0,0,0.1);
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--gray-50);
  color: var(--gray-900);
  line-height: 1.6;
}

.main-content {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px 16px;
}

a { color: var(--primary); text-decoration: none; }
a:hover { text-decoration: underline; }

button {
  cursor: pointer;
  border: none;
  border-radius: var(--radius);
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 500;
  transition: background 0.15s;
}

.btn-primary { background: var(--primary); color: #fff; }
.btn-primary:hover { background: var(--primary-hover); }
.btn-danger { background: var(--danger); color: #fff; }
.btn-danger:hover { background: var(--danger-hover); }
.btn-outline {
  background: #fff;
  border: 1px solid var(--gray-300);
  color: var(--gray-700);
}
.btn-outline:hover { background: var(--gray-100); }
.btn-sm { padding: 4px 10px; font-size: 12px; }

input[type="text"], input[type="url"], textarea, select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--gray-300);
  border-radius: var(--radius);
  font-size: 14px;
  font-family: inherit;
  transition: border-color 0.15s;
}
input:focus, textarea:focus, select:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(79,70,229,0.1);
}

.card {
  background: #fff;
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 20px;
  margin-bottom: 16px;
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}
.badge-pending { background: #fef3c7; color: #92400e; }
.badge-completed { background: #d1fae5; color: #065f46; }

.form-group { margin-bottom: 16px; }
.form-group label {
  display: block;
  margin-bottom: 4px;
  font-weight: 500;
  font-size: 14px;
  color: var(--gray-700);
}

.flex { display: flex; }
.flex-wrap { flex-wrap: wrap; }
.items-center { align-items: center; }
.justify-between { justify-content: space-between; }
.gap-8 { gap: 8px; }
.gap-12 { gap: 12px; }
.gap-16 { gap: 16px; }
.mt-16 { margin-top: 16px; }
.mb-16 { margin-bottom: 16px; }

@media (max-width: 640px) {
  .main-content { padding: 16px 12px; }
}
</style>
