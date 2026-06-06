import type { HunterEvent } from "../types";

type Props = { events: HunterEvent[] };

type Evidence = { query?: string; source?: string; snippet?: string };

export function DiscoverView({ events }: Props) {
  const blueprintEvent = [...events].reverse().find((e) => e.type === "blueprint");
  const toolEvents = events.filter((e) => e.type === "tool_start" || e.type === "tool_end");

  if (!blueprintEvent) {
    return (
      <div className="panel-body">
        <div className="empty-state">
          尚未生成 Blueprint。Hunter 仍在调研中…
          {toolEvents.length > 0 && (
            <p className="muted tiny">已发起 {toolEvents.length} 次工具调用</p>
          )}
        </div>
      </div>
    );
  }

  const evidence = (blueprintEvent.evidence ?? []) as Evidence[];
  const keywords = (blueprintEvent.keywords ?? []) as string[];

  return (
    <div className="panel-body">
      <dl className="kv">
        <dt>app_name</dt>
        <dd>
          <strong>{String(blueprintEvent.app_name || "—")}</strong>{" "}
          {blueprintEvent.data_quality && (
            <span className="badge">{String(blueprintEvent.data_quality)}</span>
          )}
        </dd>
        <dt>核心逻辑</dt>
        <dd>{String(blueprintEvent.core_logic || "—")}</dd>
        <dt>UI 布局</dt>
        <dd>{String(blueprintEvent.ui_layout || "—")}</dd>
        <dt>关键词</dt>
        <dd>
          <div className="chip-list">
            {keywords.map((k) => (
              <span key={k} className="chip">
                {k}
              </span>
            ))}
            {keywords.length === 0 && <span className="muted">—</span>}
          </div>
        </dd>
      </dl>

      <div>
        <h3 style={{ margin: "0.5rem 0 0.4rem", fontSize: "0.85rem", color: "#52525b" }}>
          调研证据（{blueprintEvent.evidence_count ?? evidence.length} 条）
        </h3>
        {evidence.length === 0 ? (
          <p className="muted tiny">无显式证据（可能是 assumption-only）。</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {evidence.map((row, i) => (
              <div key={i} className="evidence">
                <div className="evidence-query">Q: {row.query || "—"}</div>
                <div className="evidence-source">
                  {row.source?.startsWith("http") ? (
                    <a href={row.source} target="_blank" rel="noreferrer">
                      {row.source}
                    </a>
                  ) : (
                    row.source || "—"
                  )}
                </div>
                <div className="evidence-snippet">{row.snippet || "—"}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h3 style={{ margin: "0.75rem 0 0.4rem", fontSize: "0.85rem", color: "#52525b" }}>
          工具调用（{toolEvents.length}）
        </h3>
        {toolEvents.length === 0 ? (
          <p className="muted tiny">未捕获工具事件（可能是缓存命中）。</p>
        ) : (
          <ul className="event-log" style={{ maxHeight: 220 }}>
            {toolEvents.map((ev, i) => (
              <li key={i}>
                <div className="event-header">
                  <span className="event-tag tool">{ev.type === "tool_start" ? "→" : "✓"}</span>
                  <span className="event-title">{String(ev.tool || "")}</span>
                </div>
                {ev.type === "tool_start" && ev.args && (
                  <div className="event-detail">
                    {typeof ev.args === "string"
                      ? ev.args
                      : JSON.stringify(ev.args).slice(0, 200)}
                  </div>
                )}
                {ev.type === "tool_end" && ev.summary && (
                  <div className="event-detail">{String(ev.summary).slice(0, 200)}</div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
