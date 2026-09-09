import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it } from 'vitest';
import DiscoverView from './DiscoverView.vue';

describe('DiscoverView', () => {
  it('requires a real service connection before discovery', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/discover', component: DiscoverView },
        { path: '/ideas', component: { template: '<div>机会页</div>' } },
      ],
    });
    await router.push('/discover');
    await router.isReady();

    const wrapper = mount(DiscoverView, {
      attachTo: document.body,
      global: { plugins: [pinia, router] },
    });
    expect(wrapper.text()).toContain('第一次使用建议由你确认机会');
    await wrapper.get('input').setValue('旅行助手');
    await wrapper.get('.search-input button').trigger('click');
    expect(wrapper.text()).toContain('旅行助手');

    expect(wrapper.get('.start-button').attributes('disabled')).toBeDefined();
    expect(wrapper.text()).toContain('请先到“管理”页连接服务');

    wrapper.unmount();
  });
});
