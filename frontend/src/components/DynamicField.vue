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
      <label
        v-for="o in field.options"
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
import { computed } from 'vue'

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
