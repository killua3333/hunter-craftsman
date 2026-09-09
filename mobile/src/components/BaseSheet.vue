<script setup lang="ts">
import { X } from '@lucide/vue';
import { onBeforeUnmount, watch } from 'vue';

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    title: string;
    eyebrow?: string;
  }>(),
  { eyebrow: '' },
);

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>();

function close(): void {
  emit('update:modelValue', false);
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') close();
}

watch(
  () => props.modelValue,
  (open) => {
    document.body.classList.toggle('sheet-open', open);
    if (open) window.addEventListener('keydown', handleKeydown);
    else window.removeEventListener('keydown', handleKeydown);
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  document.body.classList.remove('sheet-open');
  window.removeEventListener('keydown', handleKeydown);
});
</script>

<template>
  <Teleport to="body">
    <Transition name="sheet-fade">
      <div v-if="modelValue" class="sheet-layer" role="presentation" @click.self="close">
        <section class="bottom-sheet" role="dialog" aria-modal="true" :aria-label="title">
          <div class="sheet-grabber" aria-hidden="true"></div>
          <header class="sheet-header">
            <div>
              <p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p>
              <h2>{{ title }}</h2>
            </div>
            <button type="button" class="icon-button" aria-label="关闭" @click="close">
              <X :size="20" />
            </button>
          </header>
          <div class="sheet-content">
            <slot />
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
