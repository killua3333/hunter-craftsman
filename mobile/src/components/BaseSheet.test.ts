import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import BaseSheet from './BaseSheet.vue';

describe('BaseSheet', () => {
  it('locks background scrolling and closes with Escape', async () => {
    const wrapper = mount(BaseSheet, {
      attachTo: document.body,
      props: { modelValue: true, title: '测试弹层' },
      slots: { default: '<p>弹层内容</p>' },
    });

    expect(document.body.classList.contains('sheet-open')).toBe(true);
    expect(document.body.textContent).toContain('弹层内容');

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]]);

    wrapper.unmount();
    expect(document.body.classList.contains('sheet-open')).toBe(false);
  });
});
