<script setup lang="ts">
import { ArrowRight, TrendingUp } from '@lucide/vue';
import { useRouter } from 'vue-router';
import { useWorkbenchStore } from '../stores/workbench';

const router = useRouter();
const store = useWorkbenchStore();
</script>

<template>
  <section class="page home-page">
    <header class="home-heading">
      <p>收益总览</p>
      <h1>赚了多少钱</h1>
    </header>

    <article class="profit-card">
      <span class="profit-card__label">累计净利润</span>
      <strong class="profit-amount">¥{{ store.business.profit.toLocaleString() }}</strong>
      <span class="profit-change"><TrendingUp :size="14" /> {{ store.service.status === 'connected' ? '数据已同步' : '连接服务后显示' }}</span>

      <div class="profit-breakdown">
        <span>
          <small>累计收入</small>
          <strong>¥{{ store.business.revenue.toLocaleString() }}</strong>
        </span>
        <i aria-hidden="true">−</i>
        <span>
          <small>生产成本</small>
          <strong>¥{{ store.business.productionCost.toLocaleString() }}</strong>
        </span>
        <i aria-hidden="true">=</i>
        <span>
          <small>净利润</small>
          <strong class="positive">¥{{ store.business.profit.toLocaleString() }}</strong>
        </span>
      </div>
    </article>

    <button type="button" class="detail-link" @click="router.push('/manage')">
      查看收益明细
      <ArrowRight :size="18" />
    </button>
  </section>
</template>

<style scoped>
.home-page {
  padding-top: 24px;
}

.home-heading {
  margin: 0 4px 22px;
}

.home-heading p {
  margin: 0 0 6px;
  color: var(--accent);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.11em;
}

.home-heading h1 {
  margin: 0;
  font-size: 28px;
  letter-spacing: -0.04em;
}

.profit-card {
  padding: 28px 22px 21px;
  border: 1px solid rgba(40, 213, 165, 0.22);
  border-radius: 26px;
  background:
    radial-gradient(circle at 90% 5%, rgba(40, 213, 165, 0.14), transparent 38%),
    rgba(255, 255, 255, 0.045);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1), 0 22px 55px rgba(0, 0, 0, 0.26);
  text-align: center;
}

.profit-card__label,
.profit-amount,
.profit-change {
  display: block;
}

.profit-card__label {
  color: var(--faint);
  font-size: 11px;
}

.profit-amount {
  margin: 10px 0 6px;
  font-size: 56px;
  line-height: 1;
  letter-spacing: -0.065em;
}

.profit-change {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--accent);
  font-size: 11px;
  font-weight: 800;
}

.profit-breakdown {
  display: grid;
  grid-template-columns: 1fr auto 1fr auto 1fr;
  align-items: center;
  gap: 8px;
  margin-top: 27px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
}

.profit-breakdown span,
.profit-breakdown small,
.profit-breakdown strong {
  display: block;
}

.profit-breakdown small {
  color: var(--faint);
  font-size: 8px;
}

.profit-breakdown strong {
  margin-top: 5px;
  font-size: 12px;
}

.profit-breakdown i {
  color: rgba(238, 248, 244, 0.28);
  font-size: 15px;
  font-style: normal;
}

.profit-breakdown .positive {
  color: var(--accent);
}

.detail-link {
  display: flex;
  width: 100%;
  min-height: 54px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 14px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.045);
  color: var(--text);
  font-size: 12px;
  font-weight: 800;
}

.detail-link:active {
  transform: scale(0.985);
}

@media (max-width: 350px) {
  .profit-amount {
    font-size: 49px;
  }

  .profit-breakdown {
    gap: 5px;
  }
}
</style>
