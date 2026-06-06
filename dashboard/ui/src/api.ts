import type {
  CraftsmanEvent,
  CraftsmanRun,
  PipelineMeta,
  PipelineSnapshot,
  PublisherRelease,
} from "./types";

const base = import.meta.env.VITE_GATEWAY_URL ?? "";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base}${path}`, init);
  if (!res.ok) {
    let detail: string;
    try {
      const body = (await res.json()) as { detail?: unknown };
      detail =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail ?? body);
    } catch {
      detail = (await res.text()).slice(0, 300);
    }
    throw new Error(`HTTP ${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export function listPipelines(limit = 30) {
  return json<{ pipelines: PipelineMeta[] }>(`/api/pipelines?limit=${limit}`);
}

export function linkRun(runId: string, releaseId?: string) {
  return json<PipelineMeta>(`/api/pipelines/link-run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId, release_id: releaseId || null }),
  });
}

export function getPipeline(pipelineId: string) {
  return json<PipelineSnapshot>(`/api/pipelines/${pipelineId}`);
}

export function getRun(runId: string) {
  return json<CraftsmanRun>(`/api/craftsman/runs/${runId}`);
}

export function getRunEvents(runId: string, afterId: number) {
  return json<{ events: CraftsmanEvent[]; next_after_id: number }>(
    `/api/craftsman/runs/${runId}/events?after_id=${afterId}&limit=200`,
  );
}

export function getRelease(releaseId: string) {
  return json<PublisherRelease>(`/api/craftsman/releases/${releaseId}`);
}

export function artifactUrl(runId: string, path: string) {
  return `${base}/api/artifacts/runs/${runId}/${path}`;
}

export type StreamHandlers = {
  hunter?: (data: unknown) => void;
  craftsman?: (data: unknown) => void;
  craftsman_run?: (data: unknown) => void;
  publisher?: (data: unknown) => void;
  release_discovered?: (data: { release_id: string }) => void;
  craftsman_error?: (data: unknown) => void;
  publisher_error?: (data: unknown) => void;
  error?: (data: unknown) => void;
  open?: () => void;
  close?: () => void;
};

export function openPipelineStream(
  pipelineId: string,
  handlers: StreamHandlers,
): () => void {
  const source = new EventSource(`${base}/api/pipelines/${pipelineId}/stream`);
  const named: Array<keyof StreamHandlers> = [
    "hunter",
    "craftsman",
    "craftsman_run",
    "publisher",
    "release_discovered",
    "craftsman_error",
    "publisher_error",
    "error",
  ];
  for (const name of named) {
    const fn = handlers[name];
    if (!fn) continue;
    source.addEventListener(name, (ev) => {
      try {
        fn(JSON.parse((ev as MessageEvent).data));
      } catch {
        fn((ev as MessageEvent).data);
      }
    });
  }
  source.onopen = () => handlers.open?.();
  source.onerror = () => handlers.error?.({ message: "SSE 连接异常，重试中…" });
  return () => {
    source.close();
    handlers.close?.();
  };
}

export async function checkHealth() {
  return json<{
    status: string;
    craftsman_reachable: boolean;
    craftsman_base_url: string;
    version: string;
  }>(`/health`);
}
