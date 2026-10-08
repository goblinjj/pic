// 「数据源」：列表、详情、以图搜图这几个页面从这里取数据和路由名，而不是直接调 api。
// 主人侧用 ownerSource；分享页（ShareLayout）provide 一个只读的，组件原样复用
import { inject } from 'vue'
import { api } from './api.js'
import { createImageSearch } from './imageSearch.js'
import { fileUrl, thumbUrl } from './thumbs.js'

export const ownerSource = {
  readonly: false,
  params: {},
  categoryId: null,
  routes: {
    list: 'LogList',
    detail: 'LogDetail',
    imageSearch: 'ImageSearch',
    imageSearchDetail: 'ImageSearchDetail',
  },
  getCategories: () => api.getCategories(),
  getCategoryFields: (cid) => api.getCategoryFields(cid),
  getLogs: (params) => api.getLogs(params),
  getLog: (id) => api.getLog(id),
  thumbUrl: (filename) => thumbUrl(filename),
  fileUrl: (filename) => fileUrl(filename),
  imageSearch: createImageSearch((file) => api.searchByImage(file)),
}

export function useSource() {
  return inject('source', ownerSource)
}
