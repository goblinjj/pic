<template>
  <div>
    <label class="mb-1.5 block text-sm font-medium text-slate-700">
      {{ field.name }}
      <span v-if="field.required" class="text-red-500">*</span>
    </label>

    <!-- textarea -->
    <textarea
      v-if="field.type === 'textarea'"
      :value="modelValue"
      @input="$emit('update:modelValue', $event.target.value)"
      rows="3"
      :placeholder="`${field.name}（可选）`"
      :class="inputClass"
    ></textarea>

    <!-- select（选项多时换成可搜索的下拉） -->
    <div v-else-if="field.type === 'select' && searchable" ref="comboRef" class="relative">
      <button
        type="button"
        @click="toggleOpen"
        :class="`${inputClass} flex items-center justify-between text-left`"
      >
        <span :class="selectedLabel ? '' : 'text-slate-400'">{{ selectedLabel || '请选择' }}</span>
        <svg class="h-4 w-4 shrink-0 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      <div
        v-if="open"
        class="absolute z-20 mt-1 w-full overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg"
      >
        <div class="border-b border-slate-100 p-2">
          <input
            ref="searchRef"
            v-model="query"
            type="search"
            :placeholder="`搜索${field.name}`"
            @keydown.enter.prevent="pickFirst"
            @keydown.esc="open = false"
            class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
          />
        </div>
        <ul class="max-h-60 overflow-y-auto py-1 text-sm">
          <li v-if="!query && modelValue !== '' && modelValue !== null">
            <button type="button" @click="pick('')" class="w-full px-3.5 py-2 text-left text-slate-400 hover:bg-slate-50">
              不选
            </button>
          </li>
          <li v-for="o in filteredOptions" :key="o.id">
            <button
              type="button"
              @click="pick(o.id)"
              class="w-full px-3.5 py-2 text-left hover:bg-slate-50"
              :class="o.id === modelValue ? 'bg-primary-50 font-medium text-primary-700' : 'text-slate-700'"
            >
              {{ o.label }}
            </button>
          </li>
          <li v-if="filteredOptions.length === 0" class="px-3.5 py-2 text-slate-400">没有匹配的选项</li>
        </ul>
      </div>
    </div>

    <!-- select -->
    <select
      v-else-if="field.type === 'select'"
      :value="modelValue === '' || modelValue === null ? '' : String(modelValue)"
      @change="onSelect($event)"
      :class="`${inputClass} appearance-none`"
    >
      <option value="">请选择</option>
      <option v-for="o in field.options" :key="o.id" :value="String(o.id)">{{ o.label }}</option>
    </select>

    <!-- multiselect -->
    <div v-else-if="field.type === 'multiselect'" class="flex flex-wrap gap-2">
      <input
        v-if="searchable"
        v-model="query"
        type="search"
        :placeholder="`搜索${field.name}`"
        @keydown.enter.prevent
        :class="inputClass"
      />
      <label
        v-for="o in visibleMultiOptions"
        :key="o.id"
        class="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border px-3 py-1.5 text-sm transition-colors"
        :class="isChecked(o.id)
          ? 'border-primary-400 bg-primary-50 text-primary-700'
          : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'"
      >
        <input
          type="checkbox"
          :checked="isChecked(o.id)"
          @change="toggle(o.id)"
          class="h-3.5 w-3.5 rounded border-slate-300 text-primary-600 focus:ring-primary-400"
        />
        {{ o.label }}
      </label>
      <p v-if="field.options.length === 0" class="text-xs text-slate-400">
        该字段还没有配置选项，请先到分类的字段管理中添加。
      </p>
      <p v-else-if="visibleMultiOptions.length === 0" class="text-xs text-slate-400">没有匹配的选项</p>
    </div>

    <!-- text / number / date -->
    <input
      v-else
      :type="inputType"
      :inputmode="field.type === 'number' ? 'decimal' : null"
      :step="field.type === 'number' ? 'any' : null"
      :value="modelValue"
      @input="$emit('update:modelValue', $event.target.value)"
      :placeholder="field.type === 'date' ? null : `${field.name}（可选）`"
      :class="inputClass"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { SEARCH_THRESHOLD, filterOptions } from '../fuzzy.js'

const props = defineProps({
  field: { type: Object, required: true },
  modelValue: { type: [String, Number, Array, null], default: '' },
})
const emit = defineEmits(['update:modelValue'])

const inputClass =
  'w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 transition-colors focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100'

const inputType = computed(() => {
  if (props.field.type === 'number') return 'number'
  if (props.field.type === 'date') return 'date'
  return 'text'
})

const searchable = computed(() => props.field.options?.length > SEARCH_THRESHOLD)
const query = ref('')
const filteredOptions = computed(() => filterOptions(props.field.options || [], query.value))

// 多选：已勾选的项即使不匹配搜索词也留着，免得用户以为选择丢了
const visibleMultiOptions = computed(() => {
  if (!query.value) return props.field.options
  const matched = new Set(filteredOptions.value.map((o) => o.id))
  return props.field.options.filter((o) => matched.has(o.id) || isChecked(o.id))
})

const selectedLabel = computed(
  () => props.field.options?.find((o) => o.id === props.modelValue)?.label || ''
)

const open = ref(false)
const comboRef = ref(null)
const searchRef = ref(null)

async function toggleOpen() {
  open.value = !open.value
  if (open.value) {
    query.value = ''
    await nextTick()
    searchRef.value?.focus()
  }
}

function pick(optionId) {
  emit('update:modelValue', optionId)
  open.value = false
}

function pickFirst() {
  if (filteredOptions.value.length) pick(filteredOptions.value[0].id)
}

function onOutside(event) {
  if (comboRef.value && !comboRef.value.contains(event.target)) open.value = false
}

watch(open, (value) => {
  if (value) document.addEventListener('pointerdown', onOutside)
  else document.removeEventListener('pointerdown', onOutside)
})
onBeforeUnmount(() => document.removeEventListener('pointerdown', onOutside))

function onSelect(event) {
  const raw = event.target.value
  emit('update:modelValue', raw === '' ? '' : Number(raw))
}

function isChecked(optionId) {
  return Array.isArray(props.modelValue) && props.modelValue.includes(optionId)
}

function toggle(optionId) {
  const next = Array.isArray(props.modelValue) ? [...props.modelValue] : []
  const index = next.indexOf(optionId)
  if (index === -1) next.push(optionId)
  else next.splice(index, 1)
  emit('update:modelValue', next)
}
</script>
