import type { HunterEvent } from "../types";

type Props = { events: HunterEvent[] };

export function GateView({ events }: Props) {
  const gateRounds = events.filter((e) => e.type === "gate_result");
  if (gateRounds.length === 0) {
    return (
      <div className="panel-body">
        <div className="empty-state">尚未进入 Gate。</div>
      </div>
    );
  }
  return (
    <div className="panel-body">
      {gateRounds.map((round, i) => {
        const reasons = (round.reasons ?? []) as string[];
        const rules = (round.suggested_rules ?? []) as string[];
        const questions = (round.open_questions ?? []) as string[];
        const status = String(round.agent_b_status || "");
        const cls = status === "accepted" ? "ok" : status === "needs_clarification" ? "warn" : "err";
        return (
          <div key={i} className="gate-round">
            <div className="gate-round-header">
              <strong>Revision {String(round.revision ?? "?")}</strong>
              <span className={`badge ${cls}`}>{status || "—"}</span>
            </div>
            {round.summary ? (
              <p className="muted tiny" style={{ margin: 0 }}>
                {String(round.summary)}
              </p>
            ) : null}
            {reasons.length > 0 && (
              <div className="gate-section">
                <h4>Reasons</h4>
                <ul>
                  {reasons.map((r, j) => (
                    <li key={j}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
            {rules.length > 0 && (
              <div className="gate-section">
                <h4>Suggested rules</h4>
                <ul>
                  {rules.map((r, j) => (
                    <li key={j}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
            {questions.length > 0 && (
              <div className="gate-section">
                <h4>Open questions</h4>
                <ul>
                  {questions.map((r, j) => (
                    <li key={j}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
