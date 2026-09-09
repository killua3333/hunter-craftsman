import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { describe, expect, it } from 'vitest';
import ManagementView from './ManagementView.vue';

describe('ManagementView', () => {
  it('shows only real service configuration and empty customer data', () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const wrapper = mount(ManagementView, { global: { plugins: [pinia] } });

    expect(wrapper.text()).toContain('上架与盈利');
    expect(wrapper.text()).toContain('服务连接');
    expect(wrapper.text()).toContain('生产成本¥0');
    expect(wrapper.text()).toContain('累计收入¥0');
    expect(wrapper.text()).not.toContain('演示数据');
    expect(wrapper.text()).not.toContain('一页专注清单');
    expect(wrapper.text()).toContain('连接服务后显示真实收益趋势');
    expect(wrapper.text()).not.toContain('盈利中');
    expect(wrapper.text()).toContain('不包含广告或推广费用');
    expect(wrapper.text()).not.toContain('每日最多投入');
    expect(wrapper.find('svg[aria-label="近七日利润曲线"]').exists()).toBe(false);
  });
});
