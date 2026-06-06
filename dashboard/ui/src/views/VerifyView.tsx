import { useState } from "react";
import { artifactUrl } from "../api";
import type { CraftsmanRun } from "../types";

type Props = {
  run: CraftsmanRun | null;
  runId: string | null;
};

export function VerifyView({ run, runId }: Props) {
  const [refreshKey, setRefreshKey] = useState(0);

  if (!runId) {
    return (
      <div className="panel-body">
        <div className="empty-state">等待 run_id…</div>
      </div>
    );
  }
  const feedback = run?.feedback;
  const status = String(run?.status ?? "");
  const ready = feedback && typeof feedback === "object";

  if (!ready) {
    return (
      <div className="panel-body">
        <div className="empty-state">
          {status === "failed" ? "实现失败，无可用预览。" : "实现进行中，完成后显示预览。"}
        </div>
      </div>
    );
  }

  const artifacts =
    (feedback as Record<string, unknown>).artifacts &&
    typeof (feedback as Record<string, unknown>).artifacts === "object"
      ? ((feedback as Record<string, unknown>).artifacts as Record<string, unknown>)
      : null;
  const local =
    artifacts?.local_paths && typeof artifacts.local_paths === "object"
      ? (artifacts.local_paths as Record<string, unknown>)
      : null;
  const shots = Array.isArray(local?.screenshots) ? (local!.screenshots as string[]) : [];
  const verification = (feedback as Record<string, unknown>).verification as string | undefined;
  const previewUrl = `${artifactUrl(runId, "preview.html")}?v=${refreshKey}`;
  const iconUrl = local?.icon ? artifactUrl(runId, "icon.png") : null;

  return (
    <div className="panel-body">
      <div className="toolbar">
        <span className="badge ok">verification: {verification ?? "—"}</span>
        {iconUrl && <img src={iconUrl} alt="icon" style={{ width: 32, height: 32, borderRadius: 6 }} />}
        <button
          type="button"
          className="secondary"
          onClick={() => setRefreshKey((k) => k + 1)}
          style={{ marginLeft: "auto" }}
        >
          刷新预览
        </button>
      </div>

      <iframe className="preview-frame" title="App Preview" src={previewUrl} />

      {shots.length > 0 && (
        <>
          <h3 style={{ margin: "0.5rem 0 0.4rem", fontSize: "0.85rem", color: "#52525b" }}>
            截图（{shots.length}）
          </h3>
          <div className="shots">
            {shots.map((s) => {
              const name = s.split(/[/\\]/).pop() || "shot.png";
              return (
                <img
                  key={name}
                  src={artifactUrl(runId, `screenshots/${name}`)}
                  alt={name}
                />
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
