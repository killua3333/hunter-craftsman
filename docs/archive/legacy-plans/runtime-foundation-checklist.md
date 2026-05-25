# Runtime Foundation Checklist (Hunter + Craftsman)

This checklist defines required runtime capabilities to move from demo execution to production-grade agent operations.

## P0 - Must Have

## Execution
- [x] Async run mode supported (`implement` + `run_id` + polling)
- [x] Execution backend abstraction added (`ExecutionBackend`)
- [x] Native build backend pool strategy (single host is not enough)

## Contracts
- [x] Unified feedback status includes `implementation_complete`
- [x] Reserved `release_handoff` contract added
- [x] Version negotiation and compatibility policy documented in API

## Reliability
- [x] Timeout-based polling implemented on Hunter side
- [x] Basic idempotency key wiring on implement API
- [x] Retry policy matrix (transport vs terminal failure) in both agents
- [x] Dead-letter handling for worker failures

## P1 - Strongly Recommended

## Observability
- [x] Structured JSON logs with `run_id`, `opportunity_id`, `revision`
- [x] Phase duration metrics
- [x] Model usage/token/cost metrics
- [x] Alerting on timeout/failure rate spikes

## Security
- [x] API auth for Craftsman endpoints beyond localhost-only mode
- [x] Secret management plan (env -> secret store)
- [x] Signed callback/webhook mandatory mode (currently optional)

## Verification
- [x] Verify stage hard gates (lint/test/build policy by backend mode)
- [x] Failure taxonomy for automated repair strategies
- [x] Artifact provenance record (`model`, `backend`, digest)

## P2 - Scale and Governance

## Environment
- [x] Reproducible execution images for build backends
- [x] Artifact storage as URI/object path (avoid local absolute paths)
- [x] Multi-worker queue model and lease-based ownership

## Governance
- [x] Human approval checkpoints before release actions
- [x] Policy checks for compliance metadata completeness
- [x] Audit log retention and replay strategy

## Third-Agent Readiness (No Implementation Yet)

- [x] Reserved API namespace `/v1/releases/*`
- [x] Reserved protocol `ReleaseBackend`
- [x] Reserved payload `release_handoff`
- [x] Handoff validation endpoint with strict schema check
- [x] Separate release-state lifecycle owned outside Craftsman
