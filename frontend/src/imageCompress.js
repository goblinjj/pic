// 上传前在浏览器里压缩图片：长边缩到 MAX_EDGE、转成 JPEG。
// 手机拍的 3~5MB 原图压完一般在 1MB 以内，经中转服务器上传能快好几倍。

const MAX_EDGE = 2560
const QUALITY = 0.85
// 已经足够小的图不重新编码，免得白白损失画质
const SKIP_BELOW_BYTES = 500 * 1024

// 同一个 File 只压一次：选图时就开始压，提交时直接复用结果
const cache = new WeakMap()
// 一次只解码一张。iOS Safari 同时解码多张千万像素的图容易内存不足导致页面崩溃
let queue = Promise.resolve()

export function compressImage(file) {
  if (!cache.has(file)) {
    const job = queue.then(() => doCompress(file))
    queue = job.catch(() => {})
    cache.set(file, job)
  }
  return cache.get(file)
}

export function compressImages(files) {
  return Promise.all(Array.from(files, compressImage))
}

// 以图搜图用：服务端只用到 800px，缩到 1024 足够，上传也快。
// 不走 cache（与上传用的压缩结果尺寸不同），也不看压缩开关
const SEARCH_MAX_EDGE = 1024

export function shrinkForSearch(file) {
  const job = queue.then(() => doCompress(file, SEARCH_MAX_EDGE, 0))
  queue = job.catch(() => {})
  return job
}

async function doCompress(file, maxEdge = MAX_EDGE, skipBelowBytes = SKIP_BELOW_BYTES) {
  // GIF 可能是动图，SVG 是矢量图，都不处理
  if (!file.type.startsWith('image/') || file.type === 'image/gif' || file.type === 'image/svg+xml') {
    return file
  }
  let img
  try {
    img = await loadImage(file)
  } catch {
    // 浏览器解码不了（比如非 Safari 下的 HEIC），就原样上传
    return file
  }
  const { naturalWidth: w, naturalHeight: h } = img
  const scale = Math.min(1, maxEdge / Math.max(w, h))
  if (scale === 1 && file.size < skipBelowBytes) return file

  const canvas = document.createElement('canvas')
  canvas.width = Math.round(w * scale)
  canvas.height = Math.round(h * scale)
  const ctx = canvas.getContext('2d')
  // JPEG 没有透明通道，透明 PNG 直接转会变黑底，先铺一层白色
  ctx.fillStyle = '#fff'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  // <img> 会按 EXIF 方向自动摆正，画到 canvas 上的就是正的，不会出现横竖颠倒
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height)

  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', QUALITY))
  canvas.width = canvas.height = 0 // 尽早释放 canvas 占的内存（iOS 上尤其重要）
  if (!blob || blob.size >= file.size) return file

  const name = file.name.replace(/\.[^.]*$/, '') + '.jpg'
  return new File([blob], name, { type: 'image/jpeg', lastModified: file.lastModified })
}

function loadImage(file) {
  const url = URL.createObjectURL(file)
  const img = new Image()
  img.src = url
  return img.decode().then(
    () => { URL.revokeObjectURL(url); return img },
    (e) => { URL.revokeObjectURL(url); throw e },
  )
}
