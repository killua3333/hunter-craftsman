import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { checkHealth, linkRun, listPipelines } from "../api";
import type { PipelineMeta } from "../types";
import { formatDate } from "../hooks/useTime";

type Health = {
  craftsman_reachable: boolean;
  craftsman_base_url: string;
  version: string;
};

export function HomePage() {
  const navigate = useNavigate();
  const [pipelines, setPipelines] = useState<PipelineMeta[]>([]);
  const [runId, setRunId] = useState("");
  const [releaseId, setReleaseId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    listPipelines()
      .then((r) => setPipelines(r.pipelines))
      .catch((e) => setError(String(e)));
    checkHealth().then(setHealth).catch(() => setHealth(null));
    const t = setInterval(() => {
      listPipelines()
        .then((r) => setPipelines(r.pipelines))
        .catch(() => undefined);
    }, 5000);
    return () => clearInterval(t);
  }, []);

  async function onLinkRun() {
    if (!runId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const meta = await linkRun(runId.trim(), releaseId.trim() || undefined);
      navigate(`/pipeline/${meta.pipeline_id}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <header className="app-header">
        <div>
          <h1>Agent Pipeline Dashboard</h1>
          <p className="muted" style={{ margin: 0 }}>
            Hunter 搜寻 · Craftsman 实现 · Publisher 发布
          </p>
        </div>
        <div className="header-meta">
          {health ? (
            <>
              <span className={`badge ${health.craftsman_reachable ? "ok" : "err"}`}>
                Craftsman {health.craftsman_reachable ? "在线" : "离线"}
              </span>
              <span className="badge">v{health.version}</span>
            </>
          ) : (
            <span className="badge warn">Gateway 状态未知</span>
          )}
        </div>
      </header>

      <main className="shell">
        <div className="home-grid">
          <section className="panel">
            <header className="panel-header">
              <h2>按 run_id 关联</h2>
              <span className="muted">已有 Craftsman run / release 时使用</span>
            </header>
            <div className="panel-body">
              <div className="form-row">
                <input
                  type="text"
                  placeholder="Craftsman run_id"
                  value={runId}
                  onChange={(e) => setRunId(e.target.value)}
                />
                <input
                  type="text"
                  placeholder="release_id（可选）"
                  value={releaseId}
                  onChange={(e) => setReleaseId(e.target.value)}
                />
                <button type="button" onClick={onLinkRun} disabled={loading || !runId.trim()}>
                  {loading ? "打开中…" : "打开"}
                </button>
              </div>
              {error && <div className="error-banner">{error}</div>}
              {health && !health.craftsman_reachable && (
                <p className="muted tiny">
                  ⚠ Craftsman 未在 {health.craftsman_base_url} 响应；请确认服务已启动。
                </p>
              )}
            </div>
          </section>

          <section className="panel">
            <header className="panel-header">
              <h2>最近流水线</h2>
              <span className="muted">{pipelines.length} 条</span>
            </header>
            {pipelines.length === 0 ? (
              <div className="empty-state">
                暂无记录。
                <br />
                运行 <code>hunter run "做一个离线番茄钟"</code> 或 <code>hunter autopilot</code> 后会出现在此。
              </div>
            ) : (
              <ul className="run-list">
                {pipelines.map((p) => (
                  <li key={p.pipeline_id}>
                    <div className="left">
                      <Link to={`/pipeline/${p.pipeline_id}`}>
                        <strong>{p.pipeline_id}</strong>
                      </Link>
                      <span className="badge">{p.mode}</span>
                      <span className={`badge ${statusBadge(p.status)}`}>{p.status}</span>
                      {p.question && (
                        <span className="muted tiny">{p.question.slice(0, 50)}</span>
                      )}
                    </div>
                    <span className="muted tiny">{formatDate(p.updated_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </main>
    </>
  );
}

function statusBadge(status: string): string {
  if (status === "complete") return "ok";
  if (status === "failed") return "err";
  if (status === "running") return "info";
  return "";
}
