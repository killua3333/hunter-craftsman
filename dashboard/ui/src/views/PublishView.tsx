import type { PublisherRelease } from "../types";

type Props = {
  release: PublisherRelease | null;
  error?: string;
  releaseId?: string | null;
};

export function PublishView({ release, error, releaseId }: Props) {
  if (error) {
    return (
      <div className="panel-body">
        <div className="error-banner">Publisher 错误：{error}</div>
      </div>
    );
  }
  if (!releaseId && !release) {
    return (
      <div className="panel-body">
        <div className="empty-state">
          未启用发布。
          <br />
          运行时加 <code>--publish</code> 可触发 Agent C。
        </div>
      </div>
    );
  }
  if (!release) {
    return (
      <div className="panel-body">
        <div className="empty-state">等待 release 状态…</div>
      </div>
    );
  }

  const status = String(release.status ?? "—");
  const agentC = String(release.agent_c_status ?? "—");
  const policy = release.policy;
  const approval = release.approval;
  const agentCDetail = (release.agent_c ?? {}) as Record<string, unknown>;
  const bundle = (agentCDetail.release_bundle ?? {}) as Record<string, unknown>;

  return (
    <div className="panel-body">
      <div className="toolbar">
        <span className="badge info">release {releaseId}</span>
        <span className={`badge ${badge(status)}`}>status: {status}</span>
        <span className={`badge ${badge(agentC)}`}>agent_c: {agentC}</span>
        {release.platform_target && (
          <span className="badge">target: {String(release.platform_target)}</span>
        )}
      </div>

      <div className="publish-meta">
        <div className="publish-meta-card">
          <div className="label">Policy</div>
          {policy ? (
            <>
              <strong>{policy.passed ? "通过" : "未通过"}</strong>
              {Array.isArray(policy.issues) && policy.issues.length > 0 && (
                <ul style={{ margin: "0.25rem 0 0", paddingLeft: "1.1rem" }}>
                  {policy.issues.map((iss, i) => (
                    <li key={i}>{iss}</li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <span className="muted">未检查</span>
          )}
        </div>

        <div className="publish-meta-card">
          <div className="label">Approval</div>
          {approval ? (
            <>
              <strong>{String(approval.decision || "—")}</strong>{" "}
              <span className="muted">by {String(approval.approved_by || "—")}</span>
            </>
          ) : (
            <span className="muted">无需审批 / 未审批</span>
          )}
        </div>

        {bundle.aab_path && (
          <div className="publish-meta-card" style={{ gridColumn: "1 / -1" }}>
            <div className="label">AAB</div>
            <code className="tiny">{String(bundle.aab_path)}</code>
          </div>
        )}

        {release.play_console_setup_path && (
          <div className="publish-meta-card" style={{ gridColumn: "1 / -1" }}>
            <div className="label">Play Console 清单</div>
            <code className="tiny">{String(release.play_console_setup_path)}</code>
          </div>
        )}
      </div>

      {release.setup_sheet && (
        <>
          <h3 style={{ margin: "0.5rem 0 0.4rem", fontSize: "0.85rem", color: "#52525b" }}>
            上架步骤
          </h3>
          <pre className="code-block">
            {String(release.setup_sheet).slice(0, 4000)}
          </pre>
        </>
      )}
    </div>
  );
}

function badge(status: string): string {
  const s = status.toLowerCase();
  if (["published", "dry_run_complete", "completed"].some((t) => s.includes(t))) return "ok";
  if (["failed", "rejected"].some((t) => s.includes(t))) return "err";
  if (s === "—") return "";
  return "info";
}
