import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it } from 'vitest';
import HomeView from './HomeView.vue';

describe('HomeView', () => {
  it('shows earned money without workflow clutter', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/home', component: HomeView },
        { path: '/ideas', component: { template: '<div>需求</div>' } },
        { path: '/builds', component: { template: '<div>工匠</div>' } },
        { path: '/manage', component: { template: '<div>管理</div>' } },
      ],
    });
    await router.push('/home');
    await router.isReady();

    const wrapper = mount(HomeView, { global: { plugins: [pinia, router] } });

    expect(wrapper.text()).toContain('赚了多少钱');
    expect(wrapper.text()).toContain('累计净利润¥0');
    expect(wrapper.text()).toContain('累计收入¥0');
    expect(wrapper.text()).toContain('生产成本¥0');
    expect(wrapper.text()).toContain('连接服务后显示');
    expect(wrapper.text()).toContain('查看收益明细');
    expect(wrapper.text()).not.toContain('Agent 实时进展');
    expect(wrapper.text()).not.toContain('投入');
  });
});
