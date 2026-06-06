export type StepName = "discover" | "gate" | "build" | "verify" | "publish";

export type WorkflowStatus = "pending" | "running" | "done" | "failed";

export type WorkflowStep = {
  name: StepName;
  label: string;
  status: WorkflowStatus;
  detail: string | null;
};

export type Workflow = {
  steps: WorkflowStep[];
  active: StepName;
  headline: string;
};

export type PipelineMeta = {
  pipeline_id: string;
  mode: string;
  status: string;
  question?: string | null;
  created_at?: string;
  updated_at?: string;
  craftsman: { run_id?: string | null; base_url?: string };
  publisher: { release_id?: string | null };
  terminal?: { agent_b_status?: string } | null;
};

export type HunterEvent = {
  ts: string;
  type: string;
  [k: string]: unknown;
};

export type CraftsmanRun = {
  run_id?: string;
  status?: string;
  phase?: string;
  phase_detail?: string;
  feedback?: Record<string, unknown> | null;
  [k: string]: unknown;
};

export type CraftsmanEvent = {
  id?: number;
  phase?: string;
  detail?: string;
  created_at?: string;
};

export type PublisherRelease = {
  status?: string;
  agent_c_status?: string;
  policy?: { passed?: boolean; issues?: string[] } | null;
  approval?: { decision?: string; approved_by?: string } | null;
  agent_c?: Record<string, unknown> | null;
  platform_target?: string;
  play_console_setup_path?: string;
  setup_sheet?: string;
  [k: string]: unknown;
};

export type PipelineSnapshot = {
  meta: PipelineMeta;
  craftsman_run?: CraftsmanRun;
  craftsman_error?: { code?: string; message?: string; status?: number };
  publisher_release?: PublisherRelease;
  publisher_error?: { code?: string; message?: string; status?: number };
  hunter_events: HunterEvent[];
  hunter_next_after_line: number;
  workflow: Workflow;
};
