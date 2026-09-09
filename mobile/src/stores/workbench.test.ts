import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it } from 'vitest';
import { defaultDiscovery } from '../data/defaults';
import { useWorkbenchStore } from './workbench';

const STORAGE_KEY = 'ai-money-agents.mobile.v4';

describe('workbench store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('starts as an empty customer workspace awaiting a service connection', () => {
    const store = useWorkbenchStore();

    expect(store.candidates).toHaveLength(0);
    expect(store.tasks).toHaveLength(0);
    expect(store.business.profit).toBe(0);
    expect(store.service).toMatchObject({ mode: 'live', status: 'disconnected' });
  });

  it('persists the customer service address without a token', async () => {
    const store = useWorkbenchStore();
    store.service.baseUrl = 'https://customer.example';
    await Promise.resolve();
    const persisted = localStorage.getItem(STORAGE_KEY) ?? '';
    expect(persisted).toContain('https://customer.example');
    expect(persisted).not.toContain('apiToken');
  });

  it('does not create a fake build while disconnected', async () => {
    const store = useWorkbenchStore();
    await expect(store.startBuild({ id: 'real-1', title: '真实机会', tagline: '', audience: '', painPoint: '', score: 80, trend: '', evidenceQuality: 'strong', sourceApps: 1, reviewCount: 1, features: [], saved: false })).rejects.toThrow('请先到管理页连接服务');
    expect(store.tasks).toHaveLength(0);
  });

  it('does not run fake discovery while disconnected', async () => {
    const store = useWorkbenchStore();
    await expect(store.startDiscovery(['旅行助手'], 'manual')).rejects.toThrow('请先到管理页连接服务');
    expect(store.discovery.status).toBe('idle');
  });

  it('resets an interrupted discovery instead of showing stale progress', () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        onboardingSeen: true,
        candidates: [],
        tasks: [],
        discovery: { ...defaultDiscovery, status: 'running', progress: 72, activeStep: 2 },
        service: { mode: 'live', baseUrl: 'https://customer.example' },
      }),
    );
    setActivePinia(createPinia());

    const store = useWorkbenchStore();

    expect(store.discovery).toMatchObject({ status: 'idle', progress: 0, activeStep: 0 });
    expect(store.onboardingSeen).toBe(true);
  });
});
