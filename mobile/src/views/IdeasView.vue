<script setup lang="ts">
import { Bookmark, BookmarkCheck, ChevronRight, ExternalLink, Sparkles, Star, Users } from '@lucide/vue';
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import BaseSheet from '../components/BaseSheet.vue';
import StatusPill from '../components/StatusPill.vue';
import type { Candidate, EvidenceQuality } from '../domain/types';
import { useWorkbenchStore } from '../stores/workbench';

type Filter = 'recommended' | 'all' | 'saved';

const router = useRouter();
const store = useWorkbenchStore();
const filter = ref<Filter>('recommended');
const selectedCandidate = ref<Candidate | null>(null);
const detailOpen = ref(false);
const buildError = ref('');

const filteredCandidates = computed(() => {
  if (filter.value === 'saved') return store.savedCandidates;
  if (filter.value === 'recommended') return store.candidates.filter((candidate) => candidate.score >= 80);
  return store.candidates;
});

const evidenceLabels: Record<EvidenceQuality, { label: string; tone: 'success' | 'warning' | 'neutral' }> = {
  strong: { label: '证据充分', tone: 'success' },
  medium: { label: '值得验证', tone: 'warning' },
  early: { label: '早期信号', tone: 'neutral' },
};

function openCandidate(candidate: Candidate): void {
  selectedCandidate.value = candidate;
  detailOpen.value = true;
}

async function startBuild(candidate: Candidate): Promise<void> {
  buildError.value = '';
  try { await store.startBuild(candidate); detailOpen.value = false; router.push('/builds'); }
  catch (error) { buildError.value = error instanceof Error ? error.message : '启动制作失败'; }
}
</script>

<template>
  <section class="page ideas-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">机会池</p>
        <h1>值得做的 App</h1>
      </div>
      <StatusPill tone="accent" :label="`${store.candidates.length} 个候选`" />
    </header>

    <div class="filter-tabs" role="tablist" aria-label="机会筛选">
      <button type="button" :class="{ active: filter === 'recommended' }" @click="filter = 'recommended'">推荐</button>
      <button type="button" :class="{ active: filter === 'all' }" @click="filter = 'all'">全部</button>
      <button type="button" :class="{ active: filter === 'saved' }" @click="filter = 'saved'">已收藏</button>
    </div>

    <div v-if="filteredCandidates.length" class="candidate-list">
      <article v-for="candidate in filteredCandidates" :key="candidate.id" class="glass-card candidate-card">
        <div class="candidate-card__top">
          <StatusPill :tone="evidenceLabels[candidate.evidenceQuality].tone" :label="evidenceLabels[candidate.evidenceQuality].label" />
          <button type="button" class="bookmark-button" :aria-label="candidate.saved ? '取消收藏' : '收藏机会'" @click="store.toggleSaved(candidate.id)">
            <BookmarkCheck v-if="candidate.saved" :size="19" />
            <Bookmark v-else :size="19" />
          </button>
        </div>

        <button type="button" class="candidate-card__body" @click="openCandidate(candidate)">
          <div class="candidate-card__title">
            <div>
              <h3>{{ candidate.title }}</h3>
              <p>{{ candidate.tagline }}</p>
            </div>
            <strong>{{ candidate.score }}<small>分</small></strong>
          </div>
          <div class="score-bar"><i :style="{ width: `${candidate.score}%` }"></i></div>
          <div class="candidate-stats">
            <span><ExternalLink :size="13" /> {{ candidate.sourceApps }} 个竞品</span>
            <span><Users :size="13" /> {{ candidate.reviewCount }} 条评论</span>
            <span class="trend">{{ candidate.trend }}</span>
          </div>
        </button>

        <div class="feature-list">
          <span v-for="feature in candidate.features.slice(0, 2)" :key="feature">{{ feature }}</span>
        </div>
        <button type="button" class="view-detail" @click="openCandidate(candidate)">查看判断依据 <ChevronRight :size="15" /></button>
      </article>
    </div>

    <div v-else class="empty-state">
      <span><Bookmark :size="27" /></span>
      <h2>还没有收藏</h2>
      <p>看到感兴趣的机会时，点一下书签就能留在这里。</p>
      <button type="button" class="secondary-button" @click="filter = 'recommended'">看看推荐</button>
    </div>

    <BaseSheet v-model="detailOpen" :title="selectedCandidate?.title ?? '机会详情'" eyebrow="机会判断">
      <template v-if="selectedCandidate">
        <div class="detail-score">
          <div>
            <span>综合机会分</span>
            <strong>{{ selectedCandidate.score }}</strong>
          </div>
          <StatusPill :tone="evidenceLabels[selectedCandidate.evidenceQuality].tone" :label="evidenceLabels[selectedCandidate.evidenceQuality].label" />
        </div>

        <section class="detail-section">
          <h3>适合谁</h3>
          <p>{{ selectedCandidate.audience }}</p>
        </section>
        <section class="detail-section detail-section--accent">
          <h3>用户真正难受的地方</h3>
          <p>{{ selectedCandidate.painPoint }}</p>
        </section>
        <section class="detail-section">
          <h3>建议先做这 3 个功能</h3>
          <ol>
            <li v-for="feature in selectedCandidate.features" :key="feature"><span><Star :size="13" /></span>{{ feature }}</li>
          </ol>
        </section>
        <div class="evidence-note">
          <ExternalLink :size="18" />
          <p>判断来自 {{ selectedCandidate.sourceApps }} 个 Google Play 竞品与 {{ selectedCandidate.reviewCount }} 条低分评论。</p>
        </div>
        <p v-if="buildError" class="build-error">{{ buildError }}</p>
        <button type="button" class="primary-button primary-button--wide" @click="startBuild(selectedCandidate)">
          <Sparkles :size="18" /> 开始制作这个 App
        </button>
      </template>
    </BaseSheet>
  </section>
</template>

<style scoped>
.filter-tabs {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  padding: 5px;
  border: 1px solid var(--line);
  border-radius: 17px;
  background: rgba(255, 255, 255, 0.045);
}

.filter-tabs button {
  min-height: 38px;
  border-radius: 12px;
  background: transparent;
  color: var(--faint);
  font-size: 11px;
  font-weight: 800;
}

.filter-tabs button.active {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12);
}

.candidate-list {
  display: grid;
  gap: 12px;
  margin-top: 15px;
}

.candidate-card {
  padding: 16px;
}

.candidate-card__top,
.candidate-card__title,
.candidate-stats {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.bookmark-button {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--accent);
}

.candidate-card__body {
  width: 100%;
  padding: 8px 0 0;
  background: transparent;
  color: inherit;
  text-align: left;
}

.candidate-card__title > div {
  min-width: 0;
}

.candidate-card__title h3 {
  font-size: 18px;
}

.candidate-card__title > strong {
  color: var(--accent);
  font-size: 26px;
  letter-spacing: -0.05em;
}

.candidate-card__title > strong small {
  margin-left: 2px;
  color: var(--faint);
  font-size: 9px;
  letter-spacing: 0;
}

.score-bar {
  height: 5px;
  margin: 15px 0 10px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
}

.score-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #12ad82, #36e1b2);
}

.candidate-stats {
  justify-content: flex-start;
  color: var(--faint);
  font-size: 9px;
}

.candidate-stats span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.candidate-stats .trend {
  margin-left: auto;
  color: var(--accent);
  font-weight: 900;
}

.feature-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 14px;
}

.feature-list span {
  padding: 6px 8px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.055);
  color: var(--muted);
  font-size: 9px;
}

.view-detail {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-top: 12px;
  padding: 4px 0;
  background: transparent;
  color: var(--accent);
  font-size: 10px;
  font-weight: 800;
}

.empty-state {
  padding: 58px 28px;
  text-align: center;
}

.empty-state > span {
  display: grid;
  width: 62px;
  height: 62px;
  margin: 0 auto 16px;
  place-items: center;
  border-radius: 21px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--faint);
}

.empty-state h2 {
  margin: 0 0 8px;
  font-size: 19px;
}

.empty-state p {
  margin: 0 0 18px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
}

.detail-score {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px;
  border: 1px solid rgba(40, 213, 165, 0.18);
  border-radius: 20px;
  background: rgba(40, 213, 165, 0.07);
}

.detail-score span,
.detail-score strong {
  display: block;
}

.detail-score span {
  color: var(--muted);
  font-size: 10px;
}

.detail-score strong {
  margin-top: 3px;
  color: var(--accent);
  font-size: 34px;
}

.detail-section {
  margin-top: 13px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.04);
}

.detail-section--accent {
  border-color: rgba(243, 189, 95, 0.18);
  background: rgba(243, 189, 95, 0.055);
}

.detail-section h3 {
  margin: 0 0 7px;
  font-size: 12px;
}

.detail-section p {
  margin: 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.65;
}

.detail-section ol {
  display: grid;
  gap: 9px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.detail-section li {
  display: flex;
  gap: 9px;
  align-items: center;
  color: var(--muted);
  font-size: 11px;
}

.detail-section li span {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border-radius: 8px;
  background: rgba(40, 213, 165, 0.1);
  color: var(--accent);
}

.evidence-note {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin: 14px 0 18px;
  padding: 0 4px;
  color: var(--faint);
}

.evidence-note p {
  margin: 0;
  font-size: 10px;
  line-height: 1.55;
}
</style>
