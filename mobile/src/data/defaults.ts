import type { DiscoveryState } from '../domain/types';

export const defaultDiscovery: DiscoveryState = {
  status: 'idle',
  progress: 0,
  activeStep: 0,
  mode: 'manual',
  queries: ['极简效率工具', '离线生活助手'],
  message: '连接服务后开始发现',
  runId: null,
};
