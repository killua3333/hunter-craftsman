<script setup lang="ts">
import { ArrowRight, Check, CircleDot, Radar, Search, Sparkles } from '@lucide/vue';
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import StatusPill from '../components/StatusPill.vue';
import type { DiscoveryMode } from '../domain/types';
import { useWorkbenchStore } from '../stores/workbench';

const router = useRouter();
const store = useWorkbenchStore();
const queryInput = ref('');
const selectedQueries = ref([...store.discovery.queries]);
const selectedMode = ref<DiscoveryMode>(store.discovery.mode);

const suggestions = ['学生效率', '健康提醒', '离线工具', '旅行助手'];
const modes: Array<{ value: DiscoveryMode; title: string; detail: string }> = [
  { value: 'manual', title: '我来选择', detail: '找到机会后停下来，由我确认再制作' },
  { value: 'auto', title: '自动制作', detail: '证据足够时，自动进入应用生成' },
  { value: 'auto_publish', title: '全流程', detail: '生成完成后，自动交给管理 Agent 上架' },
];
const discoverySteps = [
  { label: '搜索应用商店', detail: '找到真实竞品' },
  { label: '读取低分评论', detail: '收集用户抱怨' },
  { label: '整理核心痛点', detail: '合并重复问题' },
  { label: '生成候选机会', detail: '给出证据与评分' },
];

const canStart = computed(() => selectedQueries.value.length > 0 && store.discovery.status !== 'running' && store.service.status === 'connected');

function addQuery(value: string): void {
  const query = value.trim();
  if (query && !selectedQueries.value.includes(query)) selectedQueries.value.push(query);
  queryInput.value = '';
}

function removeQuery(value: string): void {
  selectedQueries.value = selectedQueries.value.filter((query) => query !== value);
}

async function start(): Promise<void> {
  try { await store.startDiscovery(selectedQueries.value, selectedMode.value); } catch { /* 页面显示明确错误 */ }
}
</script>

<template>
  <section class="page discover-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">Agent A · 猎手</p>
        <h1>搜索有人愿意<br />付费的需求</h1>
      </div>
      <span class="radar-icon"><Radar :size="26" /></span>
    </header>

    <template v-if="store.discovery.status === 'idle'">
      <section class="form-section">
        <div class="section-label">
          <span>1</span>
          <div><strong>选择关注方向</strong><small>可以写品类，也可以直接写一个问题</small></div>
        </div>
        <div class="search-input">
          <Search :size="19" aria-hidden="true" />
          <input v-model="queryInput" type="text" placeholder="例如：给学生用的极简工具" @keyup.enter="addQuery(queryInput)" />
          <button type="button" :disabled="!queryInput.trim()" @click="addQuery(queryInput)">添加</button>
        </div>
        <div class="chips" aria-label="已选方向">
          <button v-for="query in selectedQueries" :key="query" type="button" class="chip chip--selected" :aria-label="`移除 ${query}`" @click="removeQuery(query)">
            {{ query }} <span>×</span>
          </button>
        </div>
        <div class="suggestions">
          <span>试试：</span>
          <button v-for="item in suggestions" :key="item" type="button" class="chip" @click="addQuery(item)">{{ item }}</button>
        </div>
      </section>

      <section class="form-section">
        <div class="section-label">
          <span>2</span>
          <div><strong>决定自动到哪一步</strong><small>第一次使用建议由你确认机会</small></div>
        </div>
        <div class="mode-list">
          <button v-for="mode in modes" :key="mode.value" type="button" :class="['mode-card', { selected: selectedMode === mode.value }]" @click="selectedMode = mode.value">
            <span class="mode-radio"><Check v-if="selectedMode === mode.value" :size="14" /></span>
            <span><strong>{{ mode.title }}</strong><small>{{ mode.detail }}</small></span>
          </button>
        </div>
      </section>

      <button type="button" class="primary-button primary-button--wide start-button" :disabled="!canStart" @click="start">
        <Sparkles :size="18" />
        开始发现
        <ArrowRight :size="18" />
      </button>
      <p class="privacy-hint">{{ store.service.status === 'connected' ? '将请求已连接的 Hunter-Craftsman 服务。' : '请先到“管理”页连接服务。' }}</p>
    </template>

    <section v-else class="glass-panel discovery-progress">
      <div class="discovery-progress__head">
        <div>
          <StatusPill :tone="store.discovery.status === 'complete' ? 'success' : store.discovery.status === 'failed' ? 'danger' : 'accent'" :label="store.discovery.status === 'complete' ? '发现完成' : store.discovery.status === 'failed' ? '发现失败' : '正在分析'" />
          <h2>{{ store.discovery.status === 'complete' ? `找到 ${store.candidates.length} 个可做的机会` : store.discovery.status === 'failed' ? '这次没有完成' : '正在听用户怎么说' }}</h2>
          <p>{{ store.discovery.message }}</p>
        </div>
        <strong>{{ store.discovery.progress }}%</strong>
      </div>
      <div class="progress-track"><i :style="{ width: `${store.discovery.progress}%` }"></i></div>
      <div class="discovery-steps">
        <div v-for="(step, index) in discoverySteps" :key="step.label" :class="['discovery-step', { done: index < store.discovery.activeStep || store.discovery.status === 'complete', active: index === store.discovery.activeStep && store.discovery.status === 'running' }]">
          <span><Check v-if="index < store.discovery.activeStep || store.discovery.status === 'complete'" :size="14" /><CircleDot v-else :size="14" /></span>
          <div><strong>{{ step.label }}</strong><small>{{ step.detail }}</small></div>
        </div>
      </div>
      <button v-if="store.discovery.status === 'complete'" type="button" class="primary-button primary-button--wide" @click="router.push('/ideas')">
        查看推荐机会 <ArrowRight :size="18" />
      </button>
      <button v-if="store.discovery.status === 'failed'" type="button" class="secondary-button primary-button--wide" @click="store.discovery.status = 'idle'">返回修改</button>
    </section>
  </section>
</template>

<style scoped>
.radar-icon {
  display: grid;
  width: 54px;
  height: 54px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid rgba(40, 213, 165, 0.25);
  border-radius: 19px;
  background: rgba(40, 213, 165, 0.09);
  color: var(--accent);
}

.form-section + .form-section {
  margin-top: 25px;
}

.section-label {
  display: flex;
  gap: 11px;
  align-items: center;
  margin: 0 2px 12px;
}

.section-label > span {
  display: grid;
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 10px;
  background: rgba(40, 213, 165, 0.12);
  color: var(--accent);
  font-size: 12px;
  font-weight: 900;
}

.section-label strong,
.section-label small {
  display: block;
}

.section-label strong {
  font-size: 14px;
}

.section-label small {
  margin-top: 2px;
  color: var(--faint);
  font-size: 10px;
}

.search-input {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 9px;
  align-items: center;
  min-height: 56px;
  padding: 0 8px 0 15px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.065);
  color: var(--faint);
}

.search-input:focus-within {
  border-color: rgba(40, 213, 165, 0.5);
  box-shadow: 0 0 0 3px rgba(40, 213, 165, 0.1);
}

.search-input input {
  width: 100%;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text);
  font-size: 13px;
}

.search-input input::placeholder {
  color: rgba(238, 248, 244, 0.34);
}

.search-input button {
  padding: 9px 12px;
  border-radius: 12px;
  background: rgba(40, 213, 165, 0.12);
  color: var(--accent);
  font-size: 11px;
  font-weight: 800;
}

.search-input button:disabled {
  opacity: 0.35;
}

.chips,
.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  align-items: center;
  margin-top: 10px;
}

.suggestions > span {
  color: var(--faint);
  font-size: 10px;
}

.chip {
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.045);
  color: var(--muted);
  font-size: 10px;
  font-weight: 700;
}

.chip--selected {
  border-color: rgba(40, 213, 165, 0.23);
  background: rgba(40, 213, 165, 0.09);
  color: var(--accent);
}

.chip--selected span {
  margin-left: 4px;
}

.mode-list {
  display: grid;
  gap: 9px;
}

.mode-card {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 12px;
  align-items: center;
  min-height: 66px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.045);
  color: var(--text);
  text-align: left;
}

.mode-card.selected {
  border-color: rgba(40, 213, 165, 0.42);
  background: rgba(40, 213, 165, 0.085);
}

.mode-card strong,
.mode-card small {
  display: block;
}

.mode-card strong {
  font-size: 13px;
}

.mode-card small {
  margin-top: 4px;
  color: var(--faint);
  font-size: 10px;
  line-height: 1.4;
}

.mode-radio {
  display: grid;
  width: 22px;
  height: 22px;
  place-items: center;
  border: 1px solid var(--line-strong);
  border-radius: 50%;
  color: var(--accent-ink);
}

.selected .mode-radio {
  border-color: var(--accent);
  background: var(--accent);
}

.start-button {
  margin-top: 26px;
}

.privacy-hint {
  margin: 10px 0 0;
  color: var(--faint);
  font-size: 10px;
  text-align: center;
}

.discovery-progress {
  padding: 21px;
}

.discovery-progress__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.discovery-progress__head h2 {
  margin: 14px 0 6px;
  font-size: 20px;
}

.discovery-progress__head p {
  margin: 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.55;
}

.discovery-progress__head > strong {
  color: var(--accent);
  font-size: 24px;
}

.progress-track {
  height: 7px;
  margin: 20px 0;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
}

.progress-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--accent-strong), #3ae8b7);
  transition: width 250ms ease;
}

.discovery-steps {
  display: grid;
  gap: 5px;
  margin-bottom: 18px;
}

.discovery-step {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 11px;
  align-items: center;
  padding: 10px;
  border-radius: 15px;
  color: var(--faint);
}

.discovery-step.active {
  background: rgba(40, 213, 165, 0.08);
  color: var(--text);
}

.discovery-step.done {
  color: var(--accent);
}

.discovery-step > span {
  display: grid;
  width: 26px;
  height: 26px;
  place-items: center;
  border: 1px solid currentColor;
  border-radius: 50%;
}

.discovery-step strong,
.discovery-step small {
  display: block;
}

.discovery-step strong {
  font-size: 12px;
}

.discovery-step small {
  margin-top: 2px;
  color: var(--faint);
  font-size: 9px;
}
</style>
