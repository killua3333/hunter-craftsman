import type { CraftsmanEvent, CraftsmanRun } from "../types";
import { formatTime } from "../hooks/useTime";

const PHASES = ["spec_normalize", "plan", "codegen", "verify", "package", "complete"];

type Props = {
  run: CraftsmanRun | null;
  events: CraftsmanEvent[];
};

function phaseClass(current: string | undefined, step: string, status: string): string {
  if (status === "failed" && current === step) return "phase-chip failed";
  if (!current) return "phase-chip";
  const idx = PHASES.indexOf(current);
  const stepIdx = PHASES.indexOf(step);
  if (stepIdx < 0) return "phase-chip";
  if (current === step) return "phase-chip active";
  if (idx > stepIdx) return "phase-chip done";
  return "phase-chip";
}

export function BuildView({ run, events }: Props) {
  if (!run) {
    return (
      <div className="panel-body">
        <div className="empty-state">尚未提交 Craftsman 实现。</div>
      </div>
    );
  }
  const status = String(run.status ?? "—");
  const phase = String(run.phase ?? "");
  return (
    <div className="panel-body">
      <div className="toolbar">
        <span className="badge info">run {run.run_id}</span>
        <span className={`badge ${status.includes("complete") ? "ok" : status === "failed" ? "err" : ""}`}>
          {status}
        </span>
        {run.phase_detail && <span className="muted tiny">{String(run.phase_detail)}</span>}
      </div>

      <div className="phase-track">
        {PHASES.map((p) => (
          <span key={p} className={phaseClass(phase, p, status)}>
            {p}
          </span>
        ))}
      </div>

      <h3 style={{ margin: "0.5rem 0 0.4rem", fontSize: "0.85rem", color: "#52525b" }}>
        阶段事件（{events.length}）
      </h3>
      {events.length === 0 ? (
        <p className="muted tiny">等待 Craftsman 推送事件…</p>
      ) : (
        <ul className="event-log" style={{ maxHeight: 360 }}>
          {[...events].reverse().map((ev, i) => (
            <li key={`${ev.id ?? i}`}>
              <div className="event-header">
                <span className="event-tag build">{ev.phase ?? "phase"}</span>
                <span className="event-title">{ev.detail ?? "—"}</span>
                <span className="event-time" style={{ marginLeft: "auto" }}>
                  {formatTime(ev.created_at)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
