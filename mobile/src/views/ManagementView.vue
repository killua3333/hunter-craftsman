<script setup lang="ts">
import { ArrowDownRight, ArrowUpRight, Hammer, RefreshCw, Rocket, Search, Server, TrendingUp } from '@lucide/vue';
import { ref } from 'vue';
import StatusPill from '../components/StatusPill.vue';
import { useWorkbenchStore } from '../stores/workbench';

const store = useWorkbenchStore();
const apiKey = ref('');
const busy = ref(false);
async function connect(): Promise<void> { busy.value = true; try { await store.connectService(apiKey.value); apiKey.value = ''; } catch { /* 状态已由 store 显示 */ } finally { busy.value = false; } }
async function refresh(): Promise<void> { busy.value = true; try { await store.refreshLive(); } catch { /* 保留现有数据并显示连接状态 */ } finally { busy.value = false; } }
</script>

<template>
  <section class="page management-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">Agent C · 管理</p>
        <h1>上架与盈利</h1>
      </div>
      <span class="manager-icon"><Rocket :size="24" /></span>
    </header>

    <article class="glass-panel service-card">
      <div class="service-card__head"><span><Server :size="18" /> 服务连接</span><StatusPill :tone="store.service.status === 'connected' ? 'success' : store.service.status === 'error' ? 'danger' : 'neutral'" :label="store.service.status === 'connected' ? '已连接' : '未连接'" /></div>
        <label>DeepSeek API Key<input v-model="apiKey" type="password" autocomplete="off" placeholder="粘贴 API Key" /></label>
        <div class="service-actions"><button class="primary-button" :disabled="busy" @click="connect">{{ busy ? '连接中…' : '连接并同步' }}</button><button v-if="store.service.status === 'connected'" class="secondary-button" :disabled="busy" @click="refresh"><RefreshCw :size="15" /> 刷新</button></div>
      <p>{{ store.service.message }}。密钥仅通过固定后台验证，不保存在手机本地。</p>
    </article>

    <article class="profit-card">
      <div class="profit-card__heading">
        <div>
          <span>累计净利润</span>
          <strong>¥{{ store.business.profit.toLocaleString() }}</strong>
          <small><TrendingUp :size="13" /> {{ store.business.weeklyChange === null ? '来自服务汇总' : `本周增长 ${store.business.weeklyChange}%` }}</small>
        </div>
        <StatusPill :tone="store.service.status === 'connected' ? 'success' : 'neutral'" :label="store.service.status === 'connected' ? '已同步' : '未同步'" />
      </div>

      <svg v-if="store.service.status === 'connected'" viewBox="0 0 360 118" role="img" aria-label="近七日利润曲线">
        <defs>
          <linearGradient id="management-profit" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#37dda9" stop-opacity=".3" />
            <stop offset="1" stop-color="#37dda9" stop-opacity="0" />
          </linearGradient>
        </defs>
        <g stroke="rgba(255,255,255,.08)" stroke-width="1">
          <path d="M0 16H360M0 52H360M0 88H360" />
        </g>
        <path d="M4 98 C34 94 45 78 72 82 S113 69 142 72 S181 52 214 58 S260 40 286 42 S324 19 356 15 L356 112 L4 112 Z" fill="url(#management-profit)" />
        <path d="M4 98 C34 94 45 78 72 82 S113 69 142 72 S181 52 214 58 S260 40 286 42 S324 19 356 15" fill="none" stroke="#37dda9" stroke-width="4" stroke-linecap="round" />
        <circle cx="356" cy="15" r="5" fill="#37dda9" />
      </svg>

      <div v-if="store.service.status === 'connected'" class="chart-days" aria-hidden="true"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div>
      <p v-else class="profit-empty">连接服务后显示真实收益趋势</p>

      <div class="profit-card__metrics">
        <span><small>生产成本</small><strong>¥{{ store.business.productionCost.toLocaleString() }}</strong></span>
        <span><small>累计收入</small><strong>¥{{ store.business.revenue.toLocaleString() }}</strong></span>
        <span><small>已回本 App</small><strong>{{ store.business.recoveredApps }} 个</strong></span>
      </div>
    </article>

    <p class="cost-note">成本仅统计 App 生成、测试与上架准备，不包含广告或推广费用。</p>

    <div class="section-heading">
      <div>
        <p class="eyebrow">App 运营</p>
        <h2>生产成本与收益</h2>
      </div>
      <span class="app-count">{{ store.portfolio.length }} 个项目</span>
    </div>

    <section class="portfolio-list">
      <article v-for="app in store.portfolio" :key="app.name" class="portfolio-card">
        <div class="portfolio-card__heading">
          <span class="app-icon" :class="`app-icon--${app.tone}`">
            <Hammer v-if="app.icon === 'hammer'" :size="20" />
            <Search v-else-if="app.icon === 'search'" :size="20" />
            <Rocket v-else :size="20" />
          </span>
          <span>
            <strong>{{ app.name }}</strong>
            <small>{{ app.statusDetail }}</small>
          </span>
          <StatusPill :tone="app.statusTone" :label="app.status" />
        </div>
        <div class="portfolio-card__numbers">
          <span><small>生产成本</small><strong>¥{{ app.productionCost }}</strong></span>
          <span><small>累计收入</small><strong>¥{{ app.revenue.toLocaleString() }}</strong></span>
          <span>
            <small>净收益</small>
            <strong :class="{ positive: app.profit > 0, negative: app.profit < 0 }">
              <ArrowUpRight v-if="app.profit > 0" :size="13" />
              <ArrowDownRight v-else-if="app.profit < 0" :size="13" />
              {{ app.profit > 0 ? '+' : app.profit < 0 ? '-' : '' }}¥{{ Math.abs(app.profit).toLocaleString() }}
            </strong>
          </span>
        </div>
      </article>
    </section>
  </section>
</template>

<style scoped>
.service-card { display: grid; gap: 12px; margin-bottom: 14px; padding: 16px; }
.service-card__head, .service-card__head > span, .service-actions { display: flex; align-items: center; gap: 8px; }
.service-card__head { justify-content: space-between; font-size: 11px; font-weight: 850; }
.service-card label { display: grid; gap: 6px; color: var(--faint); font-size: 9px; }
.service-card input { min-height: 43px; padding: 0 12px; border: 1px solid var(--line); border-radius: 13px; outline: none; background: rgba(255,255,255,.045); color: var(--text); }
.service-card p { margin: 0; color: var(--faint); font-size: 9px; line-height: 1.5; }
.service-actions button { flex: 1; justify-content: center; }
.manager-icon {
  display: grid;
  width: 50px;
  height: 50px;
  place-items: center;
  border: 1px solid rgba(40, 213, 165, 0.22);
  border-radius: 17px;
  background: rgba(40, 213, 165, 0.08);
  color: var(--accent);
}

.profit-card {
  overflow: hidden;
  padding: 19px;
  border: 1px solid rgba(40, 213, 165, 0.2);
  border-radius: 24px;
  background:
    radial-gradient(circle at 92% 0, rgba(40, 213, 165, 0.14), transparent 35%),
    rgba(255, 255, 255, 0.045);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

.profit-card__heading,
.portfolio-card__heading,
.profit-card__metrics {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.profit-empty { margin: 22px 0; color: var(--faint); font-size: 10px; text-align: center; }

.profit-card__heading span,
.profit-card__heading strong,
.profit-card__heading small {
  display: block;
}

.profit-card__heading span {
  color: var(--faint);
  font-size: 10px;
}

.profit-card__heading strong {
  margin: 5px 0 3px;
  font-size: 34px;
  letter-spacing: -0.045em;
}

.profit-card__heading small {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--accent);
  font-size: 9px;
  font-weight: 800;
}

.profit-card > svg {
  display: block;
  width: 100%;
  margin-top: 17px;
}

.chart-days {
  display: flex;
  justify-content: space-between;
  padding: 0 1px;
  color: var(--faint);
  font-size: 8px;
}

.profit-card__metrics {
  margin-top: 15px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.profit-card__metrics span {
  flex: 1;
  text-align: center;
}

.profit-card__metrics span + span {
  border-left: 1px solid var(--line);
}

.profit-card__metrics small,
.profit-card__metrics strong {
  display: block;
}

.cost-note {
  margin: 11px 4px 0;
  color: var(--faint);
  font-size: 9px;
  line-height: 1.55;
}

.profit-card__metrics small {
  color: var(--faint);
  font-size: 8px;
}

.profit-card__metrics strong {
  margin-top: 5px;
  font-size: 13px;
}

.app-count {
  color: var(--faint);
  font-size: 9px;
}

.portfolio-list {
  display: grid;
  gap: 10px;
}

.portfolio-card {
  padding: 15px;
  border: 1px solid var(--line);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.04);
}

.portfolio-card__heading {
  justify-content: flex-start;
}

.app-icon {
  display: grid;
  width: 40px;
  height: 40px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 14px;
  background: rgba(40, 213, 165, 0.1);
  color: var(--accent);
}

.app-icon--amber {
  background: rgba(243, 189, 95, 0.1);
  color: var(--amber);
}

.app-icon--blue {
  background: rgba(80, 190, 255, 0.1);
  color: #71caff;
}

.portfolio-card__heading > span:nth-child(2) {
  min-width: 0;
  flex: 1;
}

.portfolio-card__heading strong,
.portfolio-card__heading small {
  display: block;
}

.portfolio-card__heading strong {
  font-size: 12px;
}

.portfolio-card__heading small {
  overflow: hidden;
  margin-top: 4px;
  color: var(--faint);
  font-size: 8px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.portfolio-card__numbers {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.portfolio-card__numbers span {
  min-width: 0;
  text-align: center;
}

.portfolio-card__numbers span + span {
  border-left: 1px solid var(--line);
}

.portfolio-card__numbers small,
.portfolio-card__numbers strong {
  display: block;
}

.portfolio-card__numbers small {
  color: var(--faint);
  font-size: 8px;
}

.portfolio-card__numbers strong {
  margin-top: 5px;
  font-size: 11px;
}

.portfolio-card__numbers strong.positive,
.portfolio-card__numbers strong.negative {
  display: inline-flex;
  align-items: center;
  color: var(--accent);
}

.portfolio-card__numbers strong.negative {
  color: var(--danger);
}

</style>
