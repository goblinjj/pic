import { createRouter, createWebHistory } from 'vue-router'
import LogList from './views/LogList.vue'
import LogForm from './views/LogForm.vue'
import LogDetail from './views/LogDetail.vue'
import Categories from './views/Categories.vue'
import CategoryFields from './views/CategoryFields.vue'
import ImageSearch from './views/ImageSearch.vue'
import Login from './views/Login.vue'
import { ensureSession } from './auth.js'

const routes = [
  { path: '/login', name: 'Login', component: Login, meta: { public: true } },
  {
    // 详情作为列表的子路由，以卡片形式盖在列表上：列表不卸载，关掉详情时
    // 滚动位置和已加载的页数都还在。地址仍是 /logs/:id，可直接打开或刷新
    path: '/',
    name: 'LogList',
    component: LogList,
    children: [
      { path: 'logs/:id(\\d+)', name: 'LogDetail', component: LogDetail },
    ],
  },
  { path: '/logs/new', name: 'LogCreate', component: LogForm },
  { path: '/logs/:id/edit', name: 'LogEdit', component: LogForm },
  { path: '/categories', name: 'Categories', component: Categories },
  { path: '/categories/:id/fields', name: 'CategoryFields', component: CategoryFields },
  {
    // 同列表：结果上弹出详情卡片，关掉后搜索结果和滚动位置都在
    path: '/search/image',
    name: 'ImageSearch',
    component: ImageSearch,
    children: [
      { path: 'logs/:id(\\d+)', name: 'ImageSearchDetail', component: LogDetail },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    // 列表和它上面的详情卡片之间切换不动滚动条，否则一开卡片列表就跳回顶部
    if (to.matched[0] && to.matched[0] === from.matched[0]) return false
    // 从编辑页等处返回列表时回到离开时的位置（列表被 keep-alive 缓存着，内容还在）
    return savedPosition || { top: 0 }
  },
})

router.beforeEach(async (to) => {
  const user = await ensureSession()
  if (to.meta.public) return user ? { path: '/' } : true
  if (!user) return { name: 'Login', query: { redirect: to.fullPath } }
  return true
})

export default router
