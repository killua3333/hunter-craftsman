import { computed, ref, watch } from 'vue';
import { defineStore } from 'pinia';
import { defaultDiscovery } from '../data/defaults';
import { BACKEND_URL } from '../config/service';
import type { BusinessSummary, BuildStage, BuildStatus, BuildTask, Candidate, DiscoveryMode, PersistedWorkbenchState, ServiceState } from '../domain/types';
import { checkHealth, exchangeDeepSeekKey, getDiscoveryRun, getOverview, implementCandidate, startDiscoveryRun, type ApiConnection, type OverviewPayload } from '../services/craftsmanApi';

const STORAGE_KEY = 'ai-money-agents.mobile.v4';
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const obj = (value: unknown): Record<string, unknown> => value && typeof value === 'object' ? value as Record<string, unknown> : {};
const str = (value: unknown, fallback = ''): string => typeof value === 'string' && value.trim() ? value : fallback;
const num = (value: unknown, fallback = 0): number => Number.isFinite(Number(value)) ? Number(value) : fallback;
const arr = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const stateOf = (value: unknown): string => str(obj(value).status).toLowerCase();
const isDone = (value: unknown): boolean => ['done', 'completed', 'complete', 'success', 'succeeded', 'released', 'published'].includes(stateOf(value));
const isActive = (value: unknown): boolean => ['running', 'active', 'in_progress', 'building', 'queued'].includes(stateOf(value));
const stage = (id: BuildStage['id'], label: string, detail: string, status: BuildStage['status']): BuildStage => ({ id, label, detail, status });

function load(): PersistedWorkbenchState | null {
  try { const raw = localStorage.getItem(STORAGE_KEY); return raw ? JSON.parse(raw) as PersistedWorkbenchState : null; }
  catch { localStorage.removeItem(STORAGE_KEY); return null; }
}

function mapCandidate(raw: Record<string, unknown>, saved: Set<string>): Candidate {
  const scores = obj(raw.scores); const evidence = num(scores.evidence ?? raw.evidence_score);
  const id = str(raw.candidate_id ?? raw.opportunity_id ?? raw.id, `candidate-${Date.now()}`);
  return { id, title: str(raw.app_name ?? raw.title, '未命名机会'), tagline: str(raw.decision_reason ?? raw.niche, '等待补充判断依据'), audience: str(raw.target_users ?? raw.audience, '尚未明确目标用户'), painPoint: arr(raw.pain_points)[0]?.toString() ?? str(raw.pain_point, '正在整理用户痛点'), score: Math.round(num(scores.opportunity ?? raw.opportunity_score ?? raw.score)), trend: str(raw.trend, '新机会'), evidenceQuality: evidence >= 70 ? 'strong' : evidence >= 45 ? 'medium' : 'early', sourceApps: arr(raw.source_apps).length || num(raw.source_app_count), reviewCount: num(obj(raw.review_pain_summary).review_count), features: arr(raw.recommended_features ?? raw.features).map(String).slice(0, 3), saved: saved.has(id) };
}

function mapTask(raw: Record<string, unknown>): BuildTask {
  const stages = obj(raw.stages); const a = obj(stages.agent_a); const b = obj(stages.agent_b); const c = obj(stages.agent_c); const p = obj(b.production_stages); const q = obj(b.quality_report);
  const buildDone = isDone(p.core_build) && isDone(p.feature_expansion); const polishDone = isDone(p.product_polish) || isDone(p.repair) || isDone(b); const deviceVerified = Boolean(q.device_launch_verified); const releaseReady = Boolean(b.release_ready ?? q.release_ready) || (num(b.quality_score) >= 75 && deviceVerified); const released = isDone(c);
  let status: BuildStatus = 'building'; if (stateOf(b) === 'failed' || stateOf(c) === 'failed') status = 'blocked'; else if (released || releaseReady) status = 'ready'; else if (isDone(b)) status = 'review';
  const id = str(raw.run_id ?? raw.id, `build-${Date.now()}`);
  return { id, candidateId: str(raw.candidate_id ?? raw.opportunity_id, id), title: str(raw.app_name ?? raw.title, '生产任务'), status, qualityScore: b.quality_score == null ? null : num(b.quality_score), productionSpend: num(raw.production_spend), estimatedProductionCost: num(raw.estimated_production_cost), remainingMinutes: null, deviceVerified, releaseReady, releaseStatus: str(c.status) || null,
    stages: [stage('plan', isDone(a) ? '方案已确认' : '需求与方案', 'Agent A 输出产品方案与证据', isDone(a) ? 'done' : isActive(a) ? 'active' : 'waiting'), stage('build', buildDone ? '核心功能已完成' : '核心功能生成', '构建主流程与必要功能', buildDone ? 'done' : isActive(b) ? 'active' : 'waiting'), stage('polish', polishDone ? '体验打磨已完成' : '体验打磨', '检查文案、空状态与边界情况', polishDone ? 'done' : buildDone ? 'active' : 'waiting'), stage('device', deviceVerified ? '设备验收已通过' : '设备验收', '必须完成安装、启动与核心流程验证', deviceVerified ? 'done' : isDone(b) ? 'blocked' : 'waiting'), stage('package', released ? '内测包已生成' : '安装包', '质量分 ≥75 且设备验收通过后生成', released ? 'done' : releaseReady ? 'active' : 'waiting')] };
}

export const useWorkbenchStore = defineStore('workbench', () => {
  const saved = load(); const onboardingSeen = ref(saved?.onboardingSeen ?? false); const candidates = ref<Candidate[]>([]); const tasks = ref<BuildTask[]>([]); const discovery = ref(clone(defaultDiscovery));
  const business = ref<BusinessSummary>({ productionCost: 0, revenue: 0, profit: 0, weeklyChange: null, recoveredApps: 0, liveApps: 0 }); const portfolio = ref<Array<{ name: string; status: string; statusTone: 'success' | 'warning'; statusDetail: string; productionCost: number; revenue: number; profit: number; tone: string; icon: string }>>([]);
  const service = ref<ServiceState>({ mode: 'live', baseUrl: BACKEND_URL, status: 'disconnected', message: '请粘贴 DeepSeek API Key', lastSyncedAt: null }); const sessionToken = ref(''); const actionError = ref(''); let timer: ReturnType<typeof setInterval> | null = null;
  if (discovery.value.status === 'running') discovery.value = clone(defaultDiscovery);
  const readyCount = computed(() => tasks.value.filter(x => x.status === 'ready').length); const activeCount = computed(() => tasks.value.filter(x => x.status === 'building' || x.status === 'review').length); const savedCandidates = computed(() => candidates.value.filter(x => x.saved)); const topCandidate = computed(() => [...candidates.value].sort((a, b) => b.score - a.score)[0] ?? null);
  watch([onboardingSeen, candidates, tasks, discovery, service], () => localStorage.setItem(STORAGE_KEY, JSON.stringify({ onboardingSeen: onboardingSeen.value, candidates: candidates.value, tasks: tasks.value, discovery: discovery.value, service: { mode: service.value.mode, baseUrl: service.value.baseUrl } } satisfies PersistedWorkbenchState)), { deep: true });
  const connection = (): ApiConnection => ({ baseUrl: BACKEND_URL, apiToken: sessionToken.value });
  function applyOverview(payload: OverviewPayload): void { const ids = new Set(savedCandidates.value.map(x => x.id)); candidates.value = arr(payload.opportunities).map(obj).map(x => mapCandidate(x, ids)); tasks.value = arr(payload.pipeline).map(obj).map(mapTask); const summary = obj(payload.summary); const earnings = obj(summary.earnings); const revenue = num(earnings.total_earnings_estimated ?? summary.total_earnings_estimated); business.value = { productionCost: 0, revenue, profit: revenue, weeklyChange: null, recoveredApps: 0, liveApps: num(earnings.app_count ?? summary.release_count) }; portfolio.value = arr(payload.releases).map(obj).map((x, i) => ({ name: str(x.app_name ?? x.title, '发布项目'), status: str(x.status, '内部发布'), statusTone: isDone(x) ? 'success' as const : 'warning' as const, statusDetail: str(x.release_notes ?? x.detail, '仅限内部发布'), productionCost: 0, revenue: 0, profit: 0, tone: i % 2 ? 'amber' : 'green', icon: isDone(x) ? 'rocket' : 'hammer' })); }
  async function refreshLive(): Promise<void> { applyOverview(await getOverview(connection())); Object.assign(service.value, { status: 'connected', message: '服务已连接，数据已同步', lastSyncedAt: new Date().toISOString() }); }
  async function connectService(deepSeekKey: string): Promise<void> { Object.assign(service.value, { status: 'connecting', message: '正在验证 API Key…' }); actionError.value = ''; try { const exchanged = await exchangeDeepSeekKey(BACKEND_URL, deepSeekKey.trim()); sessionToken.value = exchanged.access_token; if (!sessionToken.value) throw new Error('服务器未返回访问会话'); await checkHealth(connection()); await refreshLive(); } catch (error) { sessionToken.value = ''; actionError.value = error instanceof Error ? error.message : '连接失败'; Object.assign(service.value, { status: 'error', message: actionError.value }); throw error; } }
  async function startDiscovery(queries: string[], mode: DiscoveryMode): Promise<void> {
    actionError.value = ''; if (timer) clearInterval(timer);
    if (service.value.status !== 'connected') throw new Error('请先到管理页连接服务');
    try { const result = await startDiscoveryRun(connection(), queries, mode); const runId = str(result.run_id ?? result.id); if (!runId) throw new Error('服务未返回发现任务编号'); discovery.value = { status: 'running', progress: 8, activeStep: 0, mode, queries, message: '真实发现任务已启动', runId }; timer = setInterval(async () => { try { const run = await getDiscoveryRun(connection(), runId); const status = str(run.status).toLowerCase(); discovery.value.message = str(run.message ?? run.current_step, '服务正在分析'); discovery.value.progress = Math.min(96, num(run.progress, discovery.value.progress + 8)); discovery.value.activeStep = Math.min(3, Math.floor(discovery.value.progress / 25)); if (['completed','complete','done','success'].includes(status)) { if (timer) clearInterval(timer); timer = null; Object.assign(discovery.value, { status: 'complete', progress: 100, message: '真实机会已同步' }); await refreshLive(); } else if (['failed','error','cancelled'].includes(status)) { if (timer) clearInterval(timer); timer = null; discovery.value.status = 'failed'; actionError.value = discovery.value.message; } } catch (error) { if (timer) clearInterval(timer); timer = null; discovery.value.status = 'failed'; discovery.value.message = actionError.value = error instanceof Error ? error.message : '读取进度失败'; } }, 1600); } catch (error) { discovery.value = { status: 'failed', progress: 0, activeStep: 0, mode, queries, message: error instanceof Error ? error.message : '启动失败', runId: null }; throw error; }
  }
  async function startBuild(candidate: Candidate): Promise<string> { const existing = tasks.value.find(x => x.candidateId === candidate.id); if (existing) return existing.id; if (service.value.status !== 'connected') throw new Error('请先到管理页连接服务'); const result = await implementCandidate(connection(), candidate.id); await refreshLive(); return str(result.run_id ?? result.id, candidate.id); }
  function toggleSaved(id: string): void { const item = candidates.value.find(x => x.id === id); if (item) item.saved = !item.saved; }
  return { onboardingSeen, candidates, tasks, discovery, business, portfolio, service, actionError, readyCount, activeCount, savedCandidates, topCandidate, dismissOnboarding: () => { onboardingSeen.value = true; }, toggleSaved, connectService, refreshLive, startDiscovery, startBuild };
});
