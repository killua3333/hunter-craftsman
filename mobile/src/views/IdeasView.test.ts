import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it } from 'vitest';
import IdeasView from './IdeasView.vue';

describe('IdeasView', () => {
  it('does not show fabricated opportunities before service sync', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/ideas', component: IdeasView },
        { path: '/builds', component: { template: '<div>制作页</div>' } },
      ],
    });
    await router.push('/ideas');
    await router.isReady();

    const wrapper = mount(IdeasView, {
      attachTo: document.body,
      global: { plugins: [pinia, router] },
    });
    expect(wrapper.findAll('.candidate-card')).toHaveLength(0);
    expect(wrapper.text()).toContain('还没有收藏');
    expect(wrapper.text()).not.toContain('一页专注清单');

    wrapper.unmount();
  });
});
