<script setup lang="ts">
import { App as CapacitorApp } from '@capacitor/app';
import { Capacitor } from '@capacitor/core';
import { Bell, CheckCircle2, ChevronRight, Hammer, Rocket, Search } from '@lucide/vue';
import { onMounted, onUnmounted, ref, watch } from 'vue';
import { RouterView, useRoute } from 'vue-router';
import BaseSheet from './components/BaseSheet.vue';
import BottomNav from './components/BottomNav.vue';
import { router } from './router';
import { useWorkbenchStore } from './stores/workbench';

const store = useWorkbenchStore();
const route = useRoute();
const onboardingOpen = ref(!store.onboardingSeen);
const onboardingStep = ref(0);
const notificationsOpen = ref(false);
let backButtonHandle: { remove: () => Promise<void> } | null = null;

const onboarding = [
  {
    icon: Search,
    eyebrow: 'Agent A · 猎手',
    title: '先找到有人愿意付费的需求',
    text: '猎手持续搜索竞品评论和真实抱怨，把值得做的需求整理给你。',
  },
  {
    icon: Hammer,
    eyebrow: 'Agent B · 工匠',
    title: '把需求直接生成 App',
    text: '工匠负责界面、功能、测试和安装包，你只需要查看生成进度。',
  },
  {
    icon: Rocket,
    eyebrow: 'Agent C · 管理',
    title: '上架并跟踪盈利',
    text: '管理者负责提交商店和利润监控；成本只统计 App 的生成、测试与上架准备。',
  },
];

function nextOnboarding(): void {
  if (onboardingStep.value < onboarding.length - 1) {
    onboardingStep.value += 1;
    return;
  }
  finishOnboarding();
}

function finishOnboarding(): void {
  store.dismissOnboarding();
  onboardingOpen.value = false;
}

function openBuilds(): void {
  notificationsOpen.value = false;
  router.push('/builds');
}

function openManagement(): void {
  notificationsOpen.value = false;
  router.push('/manage');
}

watch(onboardingOpen, (open) => {
  if (!open) store.dismissOnboarding();
});

onMounted(async () => {
  if (Capacitor.getPlatform() !== 'web') {
    backButtonHandle = await CapacitorApp.addListener('backButton', () => {
      if (notificationsOpen.value) {
        notificationsOpen.value = false;
        return;
      }
      if (onboardingOpen.value) {
        finishOnboarding();
        return;
      }
      if (route.path === '/home') {
        CapacitorApp.exitApp();
        return;
      }
      router.back();
    });
  }
});

onUnmounted(async () => {
  await backButtonHandle?.remove();
});
</script>

<template>
  <main class="app-shell">
    <div class="app-frame">
      <header class="app-header">
        <RouterLink to="/home" class="brand" aria-label="返回首页">
          <span class="brand__mark">AI</span>
          <span>
            <strong>ai帮我赚钱</strong>
            <small>AI Money Agents</small>
          </span>
        </RouterLink>
        <button type="button" class="icon-button notification-button" aria-label="通知" @click="notificationsOpen = true">
          <Bell :size="20" />
          <span aria-hidden="true"></span>
        </button>
      </header>

      <RouterView v-slot="{ Component }">
        <Transition name="page" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </div>
    <BottomNav />

    <BaseSheet v-model="onboardingOpen" :title="onboarding[onboardingStep].title" :eyebrow="onboarding[onboardingStep].eyebrow">
      <div class="onboarding">
        <div class="onboarding__icon">
          <component :is="onboarding[onboardingStep].icon" :size="32" />
        </div>
        <p>{{ onboarding[onboardingStep].text }}</p>
        <div class="onboarding__dots" aria-label="引导进度">
          <span v-for="(_, index) in onboarding" :key="index" :class="{ active: index === onboardingStep }"></span>
        </div>
        <button type="button" class="primary-button primary-button--wide" @click="nextOnboarding">
          {{ onboardingStep === onboarding.length - 1 ? '开始使用' : '下一步' }}
          <ChevronRight :size="19" />
        </button>
        <button v-if="onboardingStep < onboarding.length - 1" type="button" class="text-button" @click="finishOnboarding">跳过引导</button>
      </div>
    </BaseSheet>

    <BaseSheet v-model="notificationsOpen" :title="store.service.status === 'connected' ? '运行状态' : '尚未连接服务'" eyebrow="消息中心">
      <div class="notice-summary">
        <span><CheckCircle2 :size="27" /></span>
        <h3>{{ store.service.status === 'connected' ? '服务运行正常' : '连接后才能开始工作' }}</h3>
        <p>{{ store.service.status === 'connected' ? `当前有 ${store.activeCount} 个制作任务，累计净利润 ¥${store.business.profit.toLocaleString()}。` : '请先粘贴 DeepSeek API Key，连接供应商后台。' }}</p>
        <button v-if="store.service.status === 'connected'" type="button" class="secondary-button secondary-button--wide" @click="openBuilds">查看制作进度 <ChevronRight :size="17" /></button>
        <button v-else type="button" class="secondary-button secondary-button--wide" @click="openManagement">配置服务 <ChevronRight :size="17" /></button>
      </div>
    </BaseSheet>
  </main>
</template>

<style scoped>
.notice-summary {
  padding: 8px 0 3px;
  text-align: center;
}

.notice-summary > span {
  display: grid;
  width: 64px;
  height: 64px;
  margin: 0 auto 15px;
  place-items: center;
  border-radius: 22px;
  background: rgba(40, 213, 165, 0.1);
  color: var(--accent);
}

.notice-summary h3 {
  margin: 0 0 7px;
  font-size: 16px;
}

.notice-summary p {
  max-width: 310px;
  margin: 0 auto 20px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.6;
}
</style>
