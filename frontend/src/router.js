import { createRouter, createWebHistory } from 'vue-router'
import LogList from './views/LogList.vue'
import LogForm from './views/LogForm.vue'
import LogDetail from './views/LogDetail.vue'
import Categories from './views/Categories.vue'
import CategoryFields from './views/CategoryFields.vue'
import ImageSearch from './views/ImageSearch.vue'

const routes = [
  { path: '/', name: 'LogList', component: LogList },
  { path: '/logs/new', name: 'LogCreate', component: LogForm },
  { path: '/logs/:id/edit', name: 'LogEdit', component: LogForm },
  { path: '/logs/:id', name: 'LogDetail', component: LogDetail },
  { path: '/categories', name: 'Categories', component: Categories },
  { path: '/categories/:id/fields', name: 'CategoryFields', component: CategoryFields },
  { path: '/search/image', name: 'ImageSearch', component: ImageSearch },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
