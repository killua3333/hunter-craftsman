export type DiscoveryMode = 'manual' | 'auto' | 'auto_publish';
export type DiscoveryStatus = 'idle' | 'running' | 'complete' | 'failed';
export type EvidenceQuality = 'strong' | 'medium' | 'early';
export type BuildStatus = 'building' | 'review' | 'ready' | 'blocked';
export type StageStatus = 'done' | 'active' | 'waiting' | 'blocked';
export type WorkspaceMode = 'demo' | 'live';
export type ConnectionStatus = 'demo' | 'disconnected' | 'connecting' | 'connected' | 'error';

export interface Candidate {
  id: string;
  title: string;
  tagline: string;
  audience: string;
  painPoint: string;
  score: number;
  trend: string;
  evidenceQuality: EvidenceQuality;
  sourceApps: number;
  reviewCount: number;
  features: string[];
  saved: boolean;
}

export interface BuildStage {
  id: 'plan' | 'build' | 'polish' | 'device' | 'package';
  label: string;
  detail: string;
  status: StageStatus;
}

export interface BuildTask {
  id: string;
  candidateId: string;
  title: string;
  status: BuildStatus;
  qualityScore: number | null;
  productionSpend: number;
  estimatedProductionCost: number;
  remainingMinutes: number | null;
  deviceVerified: boolean;
  releaseReady: boolean;
  releaseStatus: string | null;
  stages: BuildStage[];
}

export interface DiscoveryState {
  status: DiscoveryStatus;
  progress: number;
  activeStep: number;
  mode: DiscoveryMode;
  queries: string[];
  message: string;
  runId: string | null;
}

export interface BusinessSummary {
  productionCost: number;
  revenue: number;
  profit: number;
  weeklyChange: number | null;
  recoveredApps: number;
  liveApps: number;
}

export interface ServiceState {
  mode: WorkspaceMode;
  baseUrl: string;
  status: ConnectionStatus;
  message: string;
  lastSyncedAt: string | null;
}

export interface PersistedWorkbenchState {
  onboardingSeen: boolean;
  candidates: Candidate[];
  tasks: BuildTask[];
  discovery: DiscoveryState;
  service: Pick<ServiceState, 'mode' | 'baseUrl'>;
}
