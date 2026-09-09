<script setup lang="ts">
import { AlertCircle, Check, ChevronDown, ChevronRight, Hammer, LoaderCircle, ShieldCheck } from '@lucide/vue';
import { computed, ref, watch } from 'vue';
import BaseSheet from '../components/BaseSheet.vue';
import StatusPill from '../components/StatusPill.vue';
import type { BuildStatus } from '../domain/types';
import { useWorkbenchStore } from '../stores/workbench';

const store = useWorkbenchStore();
const selectedId = ref(store.tasks[0]?.id ?? '');
const outcomeOpen = ref(false);
const selectedTask = computed(() => store.tasks.find((task) => task.id === selectedId.value) ?? store.tasks[0] ?? null);
const completedStages = computed(() => selectedTask.value?.stages.filter((stage) => stage.status === 'done').length ?? 0);
const progress = computed(() => Math.round((completedStages.value / (selectedTask.value?.stages.length || 1)) * 100));

const statuses: Record<BuildStatus, { label: string; detail: string; tone: 'success' | 'warning' | 'danger' | 'neutral' | 'accent' }> = {
  building: { label: '正在生成页面与功能', detail: '工匠正在完成核心交互和本地数据。', tone: 'warning' },
  review: { label: '正在进行质量检查', detail: '核心功能已完成，正在验证使用体验。', tone: 'accent' },
  ready: { label: '正在生成安装包', detail: '页面和功能已完成，正在生成可安装文件。', tone: 'accent' },
  blocked: { label: '生产需要处理', detail: '当前生产遇到问题，等待工匠处理。', tone: 'danger' },
};

const visibleStages = computed(() => selectedTask.value?.stages ?? []);

watch(
  () => store.tasks.length,
  () => {
    if (!store.tasks.some((task) => task.id === selectedId.value)) selectedId.value = store.tasks[0]?.id ?? '';
  },
);

watch(selectedId, () => {
  outcomeOpen.value = false;
});
</script>

<template>
  <section class="page builds-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">Agent B · 工匠</p>
        <h1>正在生产 App</h1>
      </div>
      <span class="build-icon"><Hammer :size="25" /></span>
    </header>

    <label v-if="store.tasks.length > 1" class="task-picker">
      <span>切换制作任务</span>
      <span class="task-picker__control">
        <select v-model="selectedId" aria-label="选择制作任务">
          <option v-for="task in store.tasks" :key="task.id" :value="task.id">
            {{ task.title }} · {{ statuses[task.status].label }}
          </option>
        </select>
        <ChevronDown :size="16" />
      </span>
    </label>

    <template v-if="selectedTask">
      <article class="glass-panel build-summary">
        <p class="build-summary__kicker"><Hammer :size="14" /> 工匠正在制作</p>
        <div class="build-summary__title">
          <h2>{{ selectedTask.title }}</h2>
          <strong>{{ progress }}%</strong>
        </div>
        <StatusPill :tone="statuses[selectedTask.status].tone" :label="statuses[selectedTask.status].label" />
        <div class="progress-track" role="progressbar" :aria-valuenow="progress" aria-valuemin="0" aria-valuemax="100">
          <span :style="{ width: `${progress}%` }"></span>
        </div>
        <p class="build-summary__detail">{{ statuses[selectedTask.status].detail }}</p>
      </article>

      <div class="section-heading production-heading">
        <div>
          <p class="eyebrow">生产进度</p>
          <h2>现在做到哪里</h2>
        </div>
      </div>

      <div class="production-steps">
        <article v-for="(stage, index) in visibleStages" :key="stage.id" :class="['production-step', `production-step--${stage.status}`]">
          <span class="production-step__icon">
            <Check v-if="stage.status === 'done'" :size="16" />
            <AlertCircle v-else-if="stage.status === 'blocked'" :size="16" />
            <LoaderCircle v-else-if="stage.status === 'active'" :size="17" class="spin" />
            <span v-else>{{ index + 1 }}</span>
          </span>
          <div>
            <strong>{{ stage.label }}</strong>
            <small>{{ stage.detail }}</small>
          </div>
          <StatusPill v-if="stage.status === 'active'" tone="accent" label="进行中" />
        </article>
      </div>

      <article class="production-metrics">
        <div class="production-metrics__grid">
          <div>
            <span>生产投入</span>
            <strong>¥{{ selectedTask.productionSpend }}</strong>
          </div>
          <div>
            <span>预计总成本</span>
            <strong>¥{{ selectedTask.estimatedProductionCost }}</strong>
          </div>
          <div v-if="selectedTask.qualityScore !== null">
            <span>质量评分</span>
            <strong>{{ selectedTask.qualityScore }}</strong>
          </div>
          <div><span>设备验收</span><strong>{{ selectedTask.deviceVerified ? '通过' : '待完成' }}</strong></div>
        </div>
      </article>

      <button type="button" class="primary-button primary-button--wide outcome-button" @click="outcomeOpen = true">
        查看当前成果
        <ChevronRight :size="17" />
      </button>

      <BaseSheet v-model="outcomeOpen" eyebrow="工匠 · 当前成果" :title="selectedTask.title">
        <div class="outcome-summary">
          <div>
            <span><Check :size="16" /></span>
            <p><strong>核心成果</strong><small>主流程、核心交互和本地数据已完成</small></p>
          </div>
          <div v-if="selectedTask.qualityScore !== null">
            <span><ShieldCheck :size="16" /></span>
            <p><strong>质量评分 {{ selectedTask.qualityScore }}</strong><small>当前成果已达到内部测试标准</small></p>
          </div>
          <div>
            <span><ShieldCheck :size="16" /></span>
            <p><strong>{{ selectedTask.deviceVerified ? '设备验收已通过' : '设备验收尚未通过' }}</strong><small>质量分达到 75 且真机安装、启动和核心流程通过后，才会生成内测包。</small></p>
          </div>
          <div>
            <span><LoaderCircle :size="16" /></span>
            <p><strong>{{ statuses[selectedTask.status].label }}</strong><small>{{ statuses[selectedTask.status].detail }}</small></p>
          </div>
        </div>
      </BaseSheet>
    </template>

    <div v-else class="empty-builds">
      <span><Hammer :size="28" /></span>
      <h2>还没有制作任务</h2>
      <p>去机会池选择一个方向，就会在这里看到完整进度。</p>
      <RouterLink to="/ideas" class="secondary-button">选择机会 <ChevronRight :size="17" /></RouterLink>
    </div>
  </section>
</template>

<style scoped>
.build-icon {
  display: grid;
  width: 52px;
  height: 52px;
  place-items: center;
  border: 1px solid rgba(243, 189, 95, 0.22);
  border-radius: 18px;
  background: rgba(243, 189, 95, 0.08);
  color: var(--amber);
}

.task-picker {
  display: grid;
  gap: 7px;
  margin-bottom: 14px;
  color: var(--faint);
  font-size: 9px;
  font-weight: 800;
}

.task-picker__control {
  position: relative;
  display: flex;
  align-items: center;
}

.task-picker select {
  width: 100%;
  appearance: none;
  padding: 11px 38px 11px 13px;
  border: 1px solid var(--line);
  border-radius: 14px;
  outline: none;
  background: rgba(255, 255, 255, 0.045);
  color: var(--text);
  font: inherit;
  font-size: 11px;
}

.task-picker__control > svg {
  position: absolute;
  right: 13px;
  pointer-events: none;
}

.build-summary {
  padding: 19px;
}

.build-summary__kicker {
  display: flex;
  gap: 6px;
  align-items: center;
  margin: 0 0 10px;
  color: var(--amber);
  font-size: 9px;
  font-weight: 850;
}

.build-summary__title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 10px;
}

.build-summary__title h2,
.build-summary__title strong {
  margin: 0;
}

.build-summary__title h2 {
  font-size: 22px;
}

.build-summary__title strong {
  color: var(--accent);
  font-size: 24px;
}

.progress-track {
  height: 7px;
  margin-top: 15px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.075);
}

.progress-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--accent), #73eac6);
}

.build-summary__detail {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 10px;
  line-height: 1.5;
}

.production-heading {
  margin-top: 22px;
}

.production-steps {
  display: grid;
  gap: 8px;
}

.production-step {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 11px;
  align-items: center;
  padding: 13px;
  border: 1px solid var(--line);
  border-radius: 17px;
  background: rgba(255, 255, 255, 0.032);
}

.production-step__icon {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 1px solid var(--line-strong);
  border-radius: 11px;
  color: var(--faint);
  font-size: 10px;
  font-weight: 900;
}

.production-step strong,
.production-step small {
  display: block;
}

.production-step strong {
  margin-bottom: 4px;
  font-size: 12px;
}

.production-step small {
  color: var(--faint);
  font-size: 9px;
  line-height: 1.4;
}

.production-step--done .production-step__icon {
  border-color: var(--accent);
  background: var(--accent);
  color: var(--accent-ink);
}

.production-step--active {
  border-color: rgba(40, 213, 165, 0.28);
  background: rgba(40, 213, 165, 0.055);
}

.production-step--active .production-step__icon {
  border-color: var(--accent);
  color: var(--accent);
}

.production-step--blocked .production-step__icon {
  border-color: var(--danger);
  color: var(--danger);
}

.production-step--waiting {
  opacity: 0.62;
}

.spin {
  animation: spin 1.5s linear infinite;
}

.production-metrics {
  margin-top: 14px;
  padding: 16px;
  border: 1px solid rgba(243, 189, 95, 0.2);
  border-radius: 19px;
  background: rgba(243, 189, 95, 0.055);
}

.production-metrics__grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.production-metrics__grid div {
  min-width: 0;
  padding-right: 8px;
  border-right: 1px solid var(--line);
}

.production-metrics__grid div:last-child {
  padding-right: 0;
  border-right: 0;
}

.production-metrics__grid span,
.production-metrics__grid strong {
  display: block;
}

.production-metrics__grid span {
  margin-bottom: 5px;
  color: var(--faint);
  font-size: 8px;
}

.production-metrics__grid strong {
  font-size: 16px;
}

.outcome-button {
  margin-top: 16px;
}

.outcome-summary {
  display: grid;
  gap: 10px;
}

.outcome-summary > div {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 11px;
  align-items: center;
  padding: 13px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.035);
}

.outcome-summary > div > span {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 12px;
  background: rgba(40, 213, 165, 0.1);
  color: var(--accent);
}

.outcome-summary p,
.outcome-summary strong,
.outcome-summary small {
  display: block;
  margin: 0;
}

.outcome-summary strong {
  margin-bottom: 4px;
  font-size: 11px;
}

.outcome-summary small {
  color: var(--faint);
  font-size: 9px;
  line-height: 1.45;
}

.empty-builds {
  padding: 58px 28px;
  text-align: center;
}

.empty-builds > span {
  display: grid;
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  place-items: center;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.055);
  color: var(--faint);
}

.empty-builds h2 {
  margin: 0 0 8px;
  font-size: 19px;
}

.empty-builds p {
  margin: 0 0 18px;
  color: var(--muted);
  font-size: 11px;
}

.empty-builds a {
  text-decoration: none;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
