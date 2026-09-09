<script setup lang="ts">
withDefaults(
  defineProps<{
    tone?: 'success' | 'warning' | 'danger' | 'neutral' | 'accent';
    label: string;
  }>(),
  { tone: 'neutral' },
);
</script>

<template>
  <span class="status-pill" :class="`status-pill--${tone}`">
    <span class="status-pill__dot" aria-hidden="true"></span>
    {{ label }}
  </span>
</template>
