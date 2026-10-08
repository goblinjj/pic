// 缩略图重新生成过（文件名不变）时加 1：服务器没发缓存头，浏览器会按文件的
// 旧修改时间把旧图缓存好几天，换个地址才能让所有人立刻看到新图。
// 2 = 按 EXIF 摆正后重建（后端 thumbnail.ORIENTED_MARKER）
const THUMB_VERSION = 2

// base：主人侧 /api/files，分享页 /api/share/<token>/files
export function thumbUrl(filename, base = '/api/files') {
  return `${base}/thumbs/${encodeURIComponent(filename)}?v=${THUMB_VERSION}`
}

export function fileUrl(filename, base = '/api/files') {
  return `${base}/${encodeURIComponent(filename)}`
}
