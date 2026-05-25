# Execution Runtime Ops

## Native Backend Pool Strategy

- Config:
  - `NATIVE_BACKEND_POOL` (comma separated targets, e.g. `mac-a,mac-b,mac-c`)
  - `NATIVE_BACKEND_POOL_STRATEGY` (`round_robin` currently)
- Selection:
  - Runtime target assignment is handled by `craftsman.runtime.pool`.
  - `select_execution_backend()` chooses backend target per run and embeds target in `platform_note`.
- Provenance:
  - `release_handoff.build_provenance.backend_target` records assigned target.

## Reproducible Execution Image

- Docker assets:
  - `craftsman/Dockerfile`
  - `craftsman/.dockerignore`
- Base image:
  - `python:3.12-slim`
- Build and run:

```bash
docker build -t craftsman:local ./craftsman
docker run --rm -p 8791:8791 craftsman:local
```

- Image reference metadata:
  - `EXECUTION_IMAGE_REF` can point to your promoted registry image.
