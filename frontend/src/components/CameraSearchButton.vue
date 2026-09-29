<template>
  <span class="contents">
    <button
      type="button"
      :class="classes"
      :title="label || '拍照搜索'"
      :aria-label="label || '拍照搜索'"
      @click="sheet.open()"
    >
      <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="M6.827 6.175A2.31 2.31 0 0 1 5.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 0 0-1.134-.175 2.31 2.31 0 0 1-1.64-1.055l-.822-1.316a2.192 2.192 0 0 0-1.736-1.039 48.774 48.774 0 0 0-5.232 0 2.192 2.192 0 0 0-1.736 1.039l-.821 1.316Z" />
        <path stroke-linecap="round" stroke-linejoin="round" d="M16.5 12.75a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0ZM18.75 10.5h.008v.008h-.008V10.5Z" />
      </svg>
      <span v-if="label">{{ label }}</span>
    </button>
    <PhotoSourceSheet ref="sheet" @pick="onPick" />
  </span>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { searchByPhoto } from '../imageSearch.js'
import PhotoSourceSheet from './PhotoSourceSheet.vue'

const props = defineProps({
  // icon：搜索框旁的方形图标按钮；primary：主按钮；ghost：页眉里的文字按钮
  variant: { type: String, default: 'icon' },
  label: { type: String, default: '' },
})

const sheet = ref(null)
const route = useRoute()
const router = useRouter()

const classes = computed(() => ({
  icon: 'flex w-[42px] shrink-0 items-center justify-center self-stretch rounded-xl border border-slate-200 bg-white text-slate-500 shadow-sm transition-colors hover:bg-slate-50 hover:text-primary-600',
  primary: 'inline-flex items-center gap-1.5 rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-primary-700',
  ghost: 'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium text-primary-600 transition-colors hover:bg-primary-50',
}[props.variant]))

function onPick(files) {
  searchByPhoto(files[0])
  if (route.name !== 'ImageSearch') router.push({ name: 'ImageSearch' })
}
</script>
