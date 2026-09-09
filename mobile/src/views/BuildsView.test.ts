import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it } from 'vitest';
import BuildsView from './BuildsView.vue';

describe('BuildsView', () => {
  it('shows one clear production status and production-only costs', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/builds', component: BuildsView },
        { path: '/ideas', component: { template: '<div>机会池</div>' } },
      ],
    });
    await router.push('/builds');
    await router.isReady();

    const wrapper = mount(BuildsView, {
      attachTo: document.body,
      global: { plugins: [pinia, router] },
    });

    expect(wrapper.text()).toContain('还没有制作任务');
    expect(wrapper.text()).not.toContain('只统计生产成本');
    expect(wrapper.text()).not.toContain('不包含上架后的推广投入');
    expect(wrapper.text()).not.toContain('com.studio');

    wrapper.unmount();
  });
});
