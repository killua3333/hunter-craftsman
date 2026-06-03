# Deployment And Console Notes

## What is now available

- `GET /dashboard`:
  a black-and-white runtime console for Agent A / B / C visibility.
- `GET /dashboard/api/overview`:
  aggregated run, queue, release, and audit data for the console.
- `POST /dashboard/api/runs/{run_id}/requeue`:
  requeue a failed or dead-letter implementation run.
- `POST /dashboard/api/releases/{release_id}/requeue`:
  requeue a failed or dead-letter release submit job.

## Recommended production shape

1. Run `craftsman` as the always-on service.
2. Keep `hunter` as the trigger/orchestrator CLI or scheduled process.
3. Put a reverse proxy in front of `craftsman` for TLS and auth.
4. Set `API_TOKEN` in the host environment, not in the repo.
5. Use persistent storage for:
   - `craftsman/craftsman.db`
   - `craftsman/workspace/`
   - `craftsman/callbacks/`

## Reverse proxy expectation

- Expose `/dashboard` for operators.
- Restrict write actions:
  - `POST /dashboard/api/runs/*/requeue`
  - `POST /dashboard/api/releases/*/requeue`
- Pass `X-API-Token` only from trusted operator traffic or an internal gateway.

## Server onboarding when credentials are provided

When you later provide server access, the expected deployment path is:

1. Install Python 3.11+ and runtime dependencies.
2. Sync the repo and install `craftsman` and `hunter`.
3. Set environment variables securely in the service manager.
4. Create a long-running `craftsman` service.
5. Verify `/health` and `/dashboard`.
6. Run a `hunter autopilot --publish` smoke workflow in dry-run mode first.

## Included service assets

- systemd unit:
  `docker/systemd/craftsman.service`
- environment template:
  `docker/systemd/craftsman.env.example`
- nginx reverse proxy template:
  `docker/nginx/craftsman.conf.example`
- preflight checker:
  `docker/preflight-check.ps1`
- ubuntu bootstrap helper:
  `docker/bootstrap-ubuntu.sh`
- smoke checker:
  `docker/smoke-check.sh`
- windows/local smoke checker:
  `docker/smoke-check.ps1`
- hunter autopilot systemd assets:
  `docker/systemd/hunter-autopilot.service`
  `docker/systemd/hunter-autopilot.timer`
  `docker/systemd/hunter.env.example`

Suggested Linux placement:

1. Repository to `/opt/hunter-agent`
2. Virtualenv to `/opt/hunter-agent/.venv`
3. Env file to `/etc/hunter-craftsman/craftsman.env`
4. Unit file to `/etc/systemd/system/craftsman.service`
5. Then run:
   - `sudo systemctl daemon-reload`
   - `sudo systemctl enable craftsman`
   - `sudo systemctl start craftsman`

Or use the included installer helper:

```bash
sudo bash /opt/hunter-agent/docker/systemd/install-craftsman-service.sh /opt/hunter-agent
```

## Reverse proxy quick start

If you expose the service through Nginx, start from:

`docker/nginx/craftsman.conf.example`

Recommended production additions:

1. Add TLS with Let's Encrypt or your existing gateway.
2. Restrict write endpoints if the dashboard is internet-facing.
3. Forward an operator-side `X-API-Token` only from trusted traffic.

## Preflight

Before local smoke tests or server rollout, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\docker\preflight-check.ps1
```

It verifies that the repository, runtime entrypoints, and deployment templates are present.

On Linux, use:

```bash
bash ./docker/preflight-check.sh
```

## One-shot deploy helper

For a Linux server, you can stage the service and optional Nginx site with:

```bash
sudo bash /opt/hunter-agent/docker/deploy-craftsman.sh /opt/hunter-agent
```

To include the reverse proxy install:

```bash
INSTALL_NGINX=true sudo bash /opt/hunter-agent/docker/deploy-craftsman.sh /opt/hunter-agent
```

To also install Hunter's scheduled autopilot timer:

```bash
INSTALL_HUNTER_TIMER=true sudo bash /opt/hunter-agent/docker/deploy-craftsman.sh /opt/hunter-agent
```

Suggested rollout order on a fresh Ubuntu host:

```bash
sudo bash /opt/hunter-agent/docker/bootstrap-ubuntu.sh /opt/hunter-agent
sudo bash /opt/hunter-agent/docker/deploy-craftsman.sh /opt/hunter-agent
bash /opt/hunter-agent/docker/smoke-check.sh
```

For local Windows validation, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\docker\smoke-check.ps1
```

## Secrets rules

- Do not store server passwords, API keys, or Play credentials in git.
- Prefer environment injection or a dedicated secret store.
- If remote publishing is enabled later, keep signing and Play credentials outside this repository.
