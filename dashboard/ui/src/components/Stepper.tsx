import type { StepName, Workflow } from "../types";

type Props = {
  workflow: Workflow | null;
  activeStep: StepName;
  onSelect: (step: StepName) => void;
};

export function Stepper({ workflow, activeStep, onSelect }: Props) {
  const steps =
    workflow?.steps ??
    [
      { name: "discover", label: "Discover", status: "pending", detail: null },
      { name: "gate", label: "Gate", status: "pending", detail: null },
      { name: "build", label: "Build", status: "pending", detail: null },
      { name: "verify", label: "Verify", status: "pending", detail: null },
      { name: "publish", label: "Publish", status: "pending", detail: null },
    ];
  return (
    <nav className="stepper" aria-label="Pipeline workflow">
      {steps.map((step) => (
        <button
          key={step.name}
          type="button"
          className={`step ${step.status} ${activeStep === step.name ? "active" : ""}`}
          onClick={() => onSelect(step.name as StepName)}
        >
          <div className="step-top">
            <span className="step-bullet" />
            <span>{statusLabel(step.status)}</span>
          </div>
          <div className="step-label">{step.label}</div>
          <div className="step-detail">{step.detail ?? "—"}</div>
        </button>
      ))}
    </nav>
  );
}

function statusLabel(status: string): string {
  switch (status) {
    case "running":
      return "进行中";
    case "done":
      return "完成";
    case "failed":
      return "失败";
    default:
      return "待执行";
  }
}
