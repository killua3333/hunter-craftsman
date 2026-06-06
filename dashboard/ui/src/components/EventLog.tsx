import type { HunterEvent } from "../types";
import { formatTime } from "../hooks/useTime";

type Props = {
  events: HunterEvent[];
};

type Decoration = {
  tag: string;
  cls: string;
  title: string;
  detail?: string;
};

function decorate(ev: HunterEvent): Decoration {
  const type = String(ev.type || "unknown");
  switch (type) {
    case "pipeline_start":
      return { tag: type, cls: "hunter", title: `流水线启动 · ${ev.mode}` };
    case "tool_start":
      return {
        tag: "tool",
        cls: "tool",
        title: `调用工具 · ${ev.tool}`,
        detail:
          ev.args && typeof ev.args === "object"
            ? JSON.stringify(ev.args).slice(0, 160)
            : String(ev.args ?? ""),
      };
    case "tool_end":
      return {
        tag: "tool",
        cls: "tool",
        title: `工具完成 · ${ev.tool}`,
        detail: ev.summary ? String(ev.summary).slice(0, 160) : undefined,
      };
    case "blueprint":
      return {
        tag: "discover",
        cls: "hunter",
        title: `Blueprint · ${ev.app_name ?? "未命名"}`,
        detail: `证据 ${ev.evidence_count ?? 0} 条`,
      };
    case "gate_result":
      return {
        tag: "gate",
        cls: "gate",
        title: `Gate rev ${ev.revision} → ${ev.agent_b_status}`,
        detail: Array.isArray(ev.reasons) && ev.reasons.length > 0
          ? `原因 ${(ev.reasons as string[]).length} 条`
          : undefined,
      };
    case "craftsman_run":
      return {
        tag: "build",
        cls: "build",
        title: `提交实现 · ${ev.run_id}`,
      };
    case "craftsman_phase":
      return {
        tag: ev.phase ? String(ev.phase) : "build",
        cls: "build",
        title: `Craftsman · ${ev.phase}`,
        detail: ev.detail ? String(ev.detail) : undefined,
      };
    case "publish_start":
      return { tag: "publish", cls: "publish", title: "开始发布 (Agent C)" };
    case "publish_end":
      return {
        tag: "publish",
        cls: ev.publish_status === "failed" ? "error" : "publish",
        title: `发布结束 · ${ev.publish_status ?? "?"}`,
        detail: ev.error ? String(ev.error) : undefined,
      };
    case "pipeline_complete":
      return {
        tag: "done",
        cls: ev.status === "failed" ? "error" : "publish",
        title: `流水线结束 · ${ev.status}`,
      };
    default:
      return { tag: type, cls: "hunter", title: type };
  }
}

export function EventLog({ events }: Props) {
  if (events.length === 0) {
    return (
      <div className="empty-state">
        暂无事件。
        <br />
        启动 <code>hunter run</code> 或在首页用 run_id 关联现有运行。
      </div>
    );
  }
  return (
    <ul className="event-log">
      {[...events].reverse().map((ev, i) => {
        const dec = decorate(ev);
        return (
          <li key={`${ev.ts}-${i}`}>
            <div className="event-header">
              <span className={`event-tag ${dec.cls}`}>{dec.tag}</span>
              <span className="event-title">{dec.title}</span>
              <span className="event-time" style={{ marginLeft: "auto" }}>
                {formatTime(ev.ts)}
              </span>
            </div>
            {dec.detail && <div className="event-detail">{dec.detail}</div>}
          </li>
        );
      })}
    </ul>
  );
}
