import { useCallback, useEffect, useReducer, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getPipeline,
  getRelease,
  getRun,
  getRunEvents,
  openPipelineStream,
} from "../api";
import { EventLog } from "../components/EventLog";
import { Stepper } from "../components/Stepper";
import { BuildView } from "../views/BuildView";
import { DiscoverView } from "../views/DiscoverView";
import { GateView } from "../views/GateView";
import { PublishView } from "../views/PublishView";
import { VerifyView } from "../views/VerifyView";
import type {
  CraftsmanEvent,
  CraftsmanRun,
  HunterEvent,
  PipelineMeta,
  PublisherRelease,
  StepName,
  Workflow,
} from "../types";

const TERMINAL_RUN = new Set([
  "implementation_complete",
  "failed",
  "cancelled",
  "ready_for_release",
  "submitted",
]);

type State = {
  meta: PipelineMeta | null;
  workflow: Workflow | null;
  hunterEvents: HunterEvent[];
  craftsmanRun: CraftsmanRun | null;
  craftsmanEvents: CraftsmanEvent[];
  publisherRelease: PublisherRelease | null;
  publisherError?: string;
  craftsmanError?: string;
  topError: string | null;
  sseConnected: boolean;
};

type Action =
  | { type: "snapshot"; data: Awaited<ReturnType<typeof getPipeline>> }
  | { type: "hunter_event"; event: HunterEvent }
  | { type: "craftsman_run"; run: CraftsmanRun }
  | { type: "craftsman_event"; event: CraftsmanEvent }
  | { type: "publisher"; release: PublisherRelease }
  | { type: "publisher_error"; message: string }
  | { type: "craftsman_error"; message: string }
  | { type: "top_error"; message: string | null }
  | { type: "sse"; connected: boolean };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "snapshot": {
      const d = action.data;
      return {
        ...state,
        meta: d.meta,
        workflow: d.workflow,
        hunterEvents: d.hunter_events || [],
        craftsmanRun: d.craftsman_run ?? null,
        publisherRelease: d.publisher_release ?? null,
        craftsmanError: d.craftsman_error?.message,
        publisherError: d.publisher_error?.message,
      };
    }
    case "hunter_event": {
      return { ...state, hunterEvents: [...state.hunterEvents, action.event] };
    }
    case "craftsman_run":
      return { ...state, craftsmanRun: { ...state.craftsmanRun, ...action.run } };
    case "craftsman_event": {
      const existing = state.craftsmanEvents;
      if (action.event.id && existing.some((e) => e.id === action.event.id)) return state;
      return { ...state, craftsmanEvents: [...existing, action.event] };
    }
    case "publisher":
      return { ...state, publisherRelease: action.release, publisherError: undefined };
    case "publisher_error":
      return { ...state, publisherError: action.message };
    case "craftsman_error":
      return { ...state, craftsmanError: action.message };
    case "top_error":
      return { ...state, topError: action.message };
    case "sse":
      return { ...state, sseConnected: action.connected };
    default:
      return state;
  }
}

const initialState: State = {
  meta: null,
  workflow: null,
  hunterEvents: [],
  craftsmanRun: null,
  craftsmanEvents: [],
  publisherRelease: null,
  topError: null,
  sseConnected: false,
};

export function PipelinePage() {
  const { pipelineId } = useParams<{ pipelineId: string }>();
  const [state, dispatch] = useReducer(reducer, initialState);
  const [activeStep, setActiveStep] = useState<StepName>("discover");

  const runId = state.meta?.craftsman?.run_id ?? state.craftsmanRun?.run_id ?? null;
  const releaseId = state.meta?.publisher?.release_id ?? null;

  const refreshSnapshot = useCallback(async () => {
    if (!pipelineId) return;
    try {
      const data = await getPipeline(pipelineId);
      dispatch({ type: "snapshot", data });
      dispatch({ type: "top_error", message: null });
    } catch (e) {
      dispatch({ type: "top_error", message: String(e) });
    }
  }, [pipelineId]);

  useEffect(() => {
    refreshSnapshot();
  }, [refreshSnapshot]);

  useEffect(() => {
    if (state.workflow?.active && activeStep === "discover" && state.hunterEvents.length === 0) {
      setActiveStep(state.workflow.active);
    }
  }, [state.workflow?.active, state.hunterEvents.length, activeStep]);

  useEffect(() => {
    if (!pipelineId) return;
    const close = openPipelineStream(pipelineId, {
      open: () => dispatch({ type: "sse", connected: true }),
      hunter: (d) => dispatch({ type: "hunter_event", event: d as HunterEvent }),
      craftsman_run: (d) => dispatch({ type: "craftsman_run", run: d as CraftsmanRun }),
      craftsman: (d) => dispatch({ type: "craftsman_event", event: d as CraftsmanEvent }),
      publisher: (d) => dispatch({ type: "publisher", release: d as PublisherRelease }),
      release_discovered: () => refreshSnapshot(),
      craftsman_error: (d) => {
        const message = pickMessage(d);
        dispatch({ type: "craftsman_error", message });
      },
      publisher_error: (d) => {
        const message = pickMessage(d);
        dispatch({ type: "publisher_error", message });
      },
      error: () => dispatch({ type: "sse", connected: false }),
    });
    return close;
  }, [pipelineId, refreshSnapshot]);

  useEffect(() => {
    if (!runId) return;
    let afterId = 0;
    let stopped = false;
    const tick = async () => {
      try {
        const run = await getRun(runId);
        dispatch({ type: "craftsman_run", run });
        const body = await getRunEvents(runId, afterId);
        for (const ev of body.events || []) {
          dispatch({ type: "craftsman_event", event: ev });
        }
        afterId = body.next_after_id ?? afterId;
        const status = String(run.status || "");
        if (TERMINAL_RUN.has(status)) {
          stopped = true;
        }
      } catch (e) {
        dispatch({ type: "craftsman_error", message: String(e) });
      }
    };
    tick();
    const timer = setInterval(() => {
      if (!stopped) tick();
    }, 3000);
    return () => clearInterval(timer);
  }, [runId]);

  useEffect(() => {
    if (!releaseId) return;
    let stopped = false;
    const tick = async () => {
      try {
        const rel = await getRelease(releaseId);
        dispatch({ type: "publisher", release: rel });
        const st = String(rel.status || "").toLowerCase();
        if (["published", "dry_run_complete", "failed", "prepare_rejected"].includes(st)) {
          stopped = true;
        }
      } catch (e) {
        dispatch({ type: "publisher_error", message: String(e) });
      }
    };
    tick();
    const timer = setInterval(() => {
      if (!stopped) tick();
    }, 3000);
    return () => clearInterval(timer);
  }, [releaseId]);

  if (!pipelineId) return null;

  const view = renderActive(activeStep, state, runId);

  return (
    <>
      <header className="app-header">
        <div>
          <h1>
            <Link to="/" style={{ color: "inherit", marginRight: 8 }}>
              ←
            </Link>
            {pipelineId}
          </h1>
          {state.meta && (
            <p className="muted" style={{ margin: 0 }}>
              {state.meta.mode}
              {state.meta.question ? ` · ${state.meta.question.slice(0, 80)}` : ""}
            </p>
          )}
        </div>
        <div className="header-meta">
          <span className={`badge ${state.sseConnected ? "ok" : "warn"}`}>
            SSE {state.sseConnected ? "live" : "reconnecting"}
          </span>
          {state.meta?.status && (
            <span className={`badge ${state.meta.status === "complete" ? "ok" : state.meta.status === "failed" ? "err" : "info"}`}>
              {state.meta.status}
            </span>
          )}
        </div>
      </header>

      <div className="shell">
        <div className="headline">
          <div className="headline-text">
            {state.workflow?.headline ?? (state.topError ? "加载失败" : "等待数据…")}
          </div>
          <div className="headline-meta">
            {runId && <span>run: {runId}</span>}
            {releaseId && <span>release: {releaseId}</span>}
          </div>
        </div>

        {state.topError && <div className="error-banner">{state.topError}</div>}

        <Stepper
          workflow={state.workflow}
          activeStep={activeStep}
          onSelect={setActiveStep}
        />

        <div className="workspace">
          <section className="panel">
            <header className="panel-header">
              <h2>{stepLabel(activeStep)}</h2>
              <span className="muted">{stepHint(activeStep)}</span>
            </header>
            {view}
          </section>

          <section className="panel">
            <header className="panel-header">
              <h2>事件日志</h2>
              <span className="muted">最新在上</span>
            </header>
            <EventLog events={state.hunterEvents} />
          </section>
        </div>
      </div>
    </>
  );
}

function pickMessage(d: unknown): string {
  if (!d || typeof d !== "object") return String(d ?? "");
  const obj = d as Record<string, unknown>;
  return String(obj.message ?? obj.detail ?? JSON.stringify(obj));
}

function stepLabel(name: StepName): string {
  return {
    discover: "Discover · 机会发现",
    gate: "Gate · 需求评审",
    build: "Build · 实现",
    verify: "Verify · 预览验证",
    publish: "Publish · 发布",
  }[name];
}

function stepHint(name: StepName): string {
  return {
    discover: "Hunter ReAct + 工具调用",
    gate: "Craftsman Gate 反馈",
    build: "Craftsman 阶段事件",
    verify: "demo / preview / 截图",
    publish: "Agent C 状态机",
  }[name];
}

function renderActive(step: StepName, state: State, runId: string | null) {
  switch (step) {
    case "discover":
      return <DiscoverView events={state.hunterEvents} />;
    case "gate":
      return <GateView events={state.hunterEvents} />;
    case "build":
      return <BuildView run={state.craftsmanRun} events={state.craftsmanEvents} />;
    case "verify":
      return <VerifyView run={state.craftsmanRun} runId={runId} />;
    case "publish":
      return (
        <PublishView
          release={state.publisherRelease}
          error={state.publisherError}
          releaseId={state.meta?.publisher?.release_id}
        />
      );
    default:
      return null;
  }
}
