# Hunter + Craftsman Upgrade Architecture

## Scope

This document defines the target architecture for upgrading the existing dual-agent system.

- In scope: Hunter (Agent A) + Craftsman (Agent B)
- Out of scope (current phase): implementing a third release/publisher agent
- Goal: move from demo-only generation to verifiable implementation pipeline with durable runtime foundations

## Current Roles

- Hunter: opportunity mining, clarification loops, requirement generation
- Craftsman: gate analysis, implementation execution, artifacts output
- A/B communication: HTTP contracts (`analyze`, `implement`, `runs`)

## Target Layered Architecture

1. Decision Layer (Hunter)
   - LangGraph-driven research and clarification
   - Contract-first requirement output
   - Async orchestration toward Agent B

2. Execution Layer (Craftsman)
   - Phase-based state machine:
     - `spec_normalize`
     - `plan`
     - `codegen`
     - `verify`
     - `package`
     - `complete`
   - Execution backend abstraction for demo/native build backends

3. Contract Layer (shared)
   - Unified status vocabulary
   - Shared feedback schema
   - Reserved release handoff schema

4. Runtime Foundation Layer
   - Observability, reliability, security, and environment governance

## Key Upgrades Implemented in This Iteration

- Added execution backend abstraction:
  - `craftsman/craftsman/runtime/interfaces.py`
  - `craftsman/craftsman/runtime/backends.py`
- Added release handoff contract:
  - `craftsman/schemas/release-handoff.v1.json`
- Extended feedback schema and model with:
  - `implementation_complete`
  - `release_handoff`
- Added reserved release endpoints (no implementation):
  - `POST /v1/releases/prepare`
  - `POST /v1/releases/{release_id}/submit`
  - `GET /v1/releases/{release_id}`
- Hunter orchestration now supports async implementation path:
  - `start_implementation`
  - `wait_for_run_completion`
  - polling + timeout controls

## Status Model (Agent B)

Primary statuses for current phase:

- `needs_clarification`
- `accepted`
- `in_progress`
- `implementation_failed`
- `implementation_complete`

Legacy statuses (`ready_for_release`, `submitted`, `platform_unavailable`) remain accepted for compatibility, but release lifecycle is reserved for future dedicated release agent.

## API Interaction Model (Target in Current Phase)

1. Hunter -> `POST /v1/opportunities/{id}/analyze`
2. Hunter -> `POST /v1/opportunities/{id}/implement` (async preferred)
3. Hunter -> `GET /v1/runs/{run_id}` polling or event-based extension in next phase
4. Hunter receives terminal feedback and stores it for learning

## Reserved Interface for Future Release Agent

- Schema: `release-handoff.v1`
- Runtime protocol: `ReleaseBackend` (placeholder contract)
- API stubs exposed under `/v1/releases/*`
- No release-side execution logic in current phase

## Next Steps

1. Enforce async orchestration path as default everywhere in Hunter CLI commands.
2. Introduce phase event streaming endpoint (`SSE`) to replace pure polling.
3. Persist run-level metrics and token/cost telemetry.
4. Promote compatibility statuses to explicit API version negotiation.
