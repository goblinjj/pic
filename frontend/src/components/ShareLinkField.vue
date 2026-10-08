<template>
  <div>
    <div class="flex gap-2">
      <input
        ref="input"
        :value="url"
        readonly
        @focus="$event.target.select()"
        class="min-w-0 flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700"
      />
      <button
        type="button"
        @click="copy"
        class="shrink-0 rounded-xl bg-primary-600 px-3 py-2 text-xs font-medium text-white shadow-sm transition-colors hover:bg-primary-700"
      >
        {{ copied ? '已复制' : '复制' }}
      </button>
    </div>
    <p v-if="manual" class="mt-1.5 text-[11px] text-amber-600">已选中链接，请长按或用 Ctrl+C 复制</p>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { copyText, shareUrl } from '../shareLink.js'

const props = defineProps({ token: { type: String, required: true } })

const url = computed(() => shareUrl(props.token))
const input = ref(null)
const copied = ref(false)
const manual = ref(false)

async function copy() {
  if (await copyText(url.value)) {
    copied.value = true
    manual.value = false
    setTimeout(() => { copied.value = false }, 1500)
  } else {
    input.value.focus()
    input.value.select()
    manual.value = true
  }
}
</script>
