<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    value: number;
    size?: number;
    label?: string;
  }>(),
  { size: 82, label: '完成度' },
);

const ringStyle = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  background: `conic-gradient(var(--accent) ${Math.max(0, Math.min(100, props.value)) * 3.6}deg, rgba(255,255,255,.09) 0deg)`,
}));
</script>

<template>
  <div class="progress-ring" :style="ringStyle" role="progressbar" :aria-valuenow="value" aria-valuemin="0" aria-valuemax="100">
    <div class="progress-ring__inner">
      <strong>{{ value }}%</strong>
      <span>{{ label }}</span>
    </div>
  </div>
</template>
