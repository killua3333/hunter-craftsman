<script setup lang="ts">
import { Hammer, Home, Rocket, Search } from '@lucide/vue';

const items = [
  { to: '/home', label: '总览', icon: Home },
  { to: '/discover', label: '猎手', icon: Search },
  { to: '/builds', label: '工匠', icon: Hammer },
  { to: '/manage', label: '管理', icon: Rocket },
];
</script>

<template>
  <nav class="bottom-nav bottom-nav-offset" aria-label="主导航">
    <RouterLink v-for="item in items" :key="item.to" :to="item.to" class="bottom-nav__item">
      <component :is="item.icon" :size="21" :stroke-width="2.2" aria-hidden="true" />
      <span>{{ item.label }}</span>
    </RouterLink>
  </nav>
</template>
