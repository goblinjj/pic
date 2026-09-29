<template>
  <!-- 拍照：带 capture 直接打开后置相机 -->
  <input ref="cameraInput" type="file" accept="image/*" capture="environment" class="hidden" @change="onChange" />
  <!-- 相册：不带 capture -->
  <input ref="albumInput" type="file" accept="image/*" :multiple="multiple" class="hidden" @change="onChange" />

  <Teleport to="body">
    <div
      v-if="visible"
      class="fixed inset-0 z-[60] flex items-end justify-center bg-black/40"
      @click.self="visible = false"
    >
      <div class="w-full max-w-lg overflow-hidden rounded-t-2xl bg-white pb-[env(safe-area-inset-bottom)] text-center text-base">
        <button type="button" class="block w-full border-b border-slate-100 py-4 text-slate-900 active:bg-slate-50" @click="choose(cameraInput)">
          拍照
        </button>
        <button type="button" class="block w-full py-4 text-slate-900 active:bg-slate-50" @click="choose(albumInput)">
          从相册选择
        </button>
        <div class="h-2 bg-slate-100" />
        <button type="button" class="block w-full py-4 text-slate-500 active:bg-slate-50" @click="visible = false">
          取消
        </button>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
// 手机上先让用户选「拍照 / 从相册选择」。
// Android 版 Chrome 遇到只有 accept="image/*" 的选择框会直接打开相册、不给拍照选项
// （微信会自己弹菜单，Chrome 不会），所以菜单得由页面自己提供。
import { ref } from 'vue'

defineProps({
  multiple: { type: Boolean, default: false },
})
const emit = defineEmits(['pick'])

const visible = ref(false)
const cameraInput = ref(null)
const albumInput = ref(null)

function open() {
  // 桌面端没有「拍照」这回事，直接打开文件选择，和原来一样
  if (!window.matchMedia('(pointer: coarse)').matches) {
    albumInput.value.click()
    return
  }
  visible.value = true
}

function choose(input) {
  visible.value = false
  // 必须在这次点击的处理函数里同步调用，浏览器才允许打开选择框
  input.click()
}

function onChange(e) {
  const files = Array.from(e.target.files || [])
  // 清空，这样连续选同一张图也会触发 change
  e.target.value = ''
  if (files.length) emit('pick', files)
}

defineExpose({ open })
</script>
