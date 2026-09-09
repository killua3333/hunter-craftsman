import { CapacitorHttp } from '@capacitor/core';

export interface ApiConnection {
  baseUrl: string;
  apiToken: string;
}

export interface OverviewPayload {
  summary?: Record<string, unknown>;
  opportunities?: Array<Record<string, unknown>>;
  pipeline?: Array<Record<string, unknown>>;
  releases?: Array<Record<string, unknown>>;
}

export interface KeyExchangePayload {
  access_token: string;
  expires_in?: number;
}

function endpoint(connection: ApiConnection, path: string): string {
  const baseUrl = connection.baseUrl.trim().replace(/\/+$/, '');
  if (!/^https?:\/\//i.test(baseUrl)) throw new Error('服务地址需要以 http:// 或 https:// 开头');
  return `${baseUrl}${path}`;
}

function messageFrom(data: unknown, status: number): string {
  if (data && typeof data === 'object') {
    const payload = data as Record<string, unknown>;
    const detail = payload.detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object') {
      const message = (detail as Record<string, unknown>).message;
      if (typeof message === 'string') return message;
    }
  }
  return `服务请求失败（${status}）`;
}

async function request<T>(connection: ApiConnection, path: string, method = 'GET', data?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (connection.apiToken.trim()) headers['X-API-Token'] = connection.apiToken.trim();
  if (data !== undefined) headers['Content-Type'] = 'application/json';

  const response = await CapacitorHttp.request({
    url: endpoint(connection, path),
    method,
    headers,
    data,
    connectTimeout: 12_000,
    readTimeout: 30_000,
    responseType: 'json',
  });
  if (response.status < 200 || response.status >= 300) throw new Error(messageFrom(response.data, response.status));
  return response.data as T;
}

export function checkHealth(connection: ApiConnection): Promise<Record<string, unknown>> {
  return request(connection, '/health');
}

export function exchangeDeepSeekKey(baseUrl: string, apiKey: string): Promise<KeyExchangePayload> {
  return request({ baseUrl, apiToken: '' }, '/mobile/api/session', 'POST', {
    provider: 'deepseek',
    api_key: apiKey,
  });
}

export function getOverview(connection: ApiConnection): Promise<OverviewPayload> {
  return request(connection, '/dashboard/api/overview');
}

export function startDiscoveryRun(connection: ApiConnection, seedQueries: string[], mode: string): Promise<Record<string, unknown>> {
  return request(connection, '/dashboard/api/discovery-runs', 'POST', {
    seed_queries: seedQueries,
    categories: [],
    mode,
    operator: 'mobile-operator',
  });
}

export function getDiscoveryRun(connection: ApiConnection, runId: string): Promise<Record<string, unknown>> {
  return request(connection, `/dashboard/api/discovery-runs/${encodeURIComponent(runId)}`);
}

export function implementCandidate(connection: ApiConnection, candidateId: string): Promise<Record<string, unknown>> {
  return request(connection, `/dashboard/api/opportunities/${encodeURIComponent(candidateId)}/implement`, 'POST', {
    operator: 'mobile-operator',
    auto_release: false,
  });
}
