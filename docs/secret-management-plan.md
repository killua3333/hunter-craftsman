# Secret Management Plan (env -> secret store)

## Goal

Move sensitive values from plain environment variables toward a file-backed secret store with minimal runtime changes.

## Current Implementation

- Config switch: `SECRET_PROVIDER`
  - `env`: use environment values only
  - `file`: read from secret store files only
  - `env_file_fallback` (default): prefer env, fallback to file
- Secret directory: `SECRET_STORE_DIR` (default `./secrets`)
- Resolved at runtime via `craftsman/craftsman/secrets.py`
- Integrated secret resolution:
  - `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`
  - `API_TOKEN`
  - `WEBHOOK_SECRET`

## Secret Store File Naming

Each secret can be provided via any of these file names under `SECRET_STORE_DIR`:

- `<ENV_NAME>`
- `<ENV_NAME>.txt`
- lowercase variants (e.g. `openai_api_key`, `openai_api_key.txt`)

The file content is trimmed and used as secret value.

## Operational Recommendation

1. Local dev:
   - keep `SECRET_PROVIDER=env_file_fallback`
   - `.env` for non-sensitive defaults
   - secrets in `./secrets/*` (excluded from git)
2. CI / production:
   - mount secrets into `SECRET_STORE_DIR`
   - set `SECRET_PROVIDER=file`
   - avoid exporting long-lived secrets as plain env vars
3. Rotation:
   - write new file content atomically
   - restart worker/api process to reload settings

## Next Step (not yet implemented)

- Integrate external secret managers (Vault/KMS/SM) as additional provider modes.
