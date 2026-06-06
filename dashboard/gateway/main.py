"""Pipeline operations dashboard gateway."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from artifacts import artifact_file
from craftsman_client import craftsman_health, craftsman_request
from pipeline_store import (
    attach_release,
    list_pipeline_metas,
    load_meta,
    read_hunter_events,
    upsert_meta_from_run,
)
from settings import settings
from workflow import derive_workflow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("dashboard")

app = FastAPI(title="Agent Pipeline Dashboard", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        f"http://{settings.host}:{settings.port}",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LinkRunBody(BaseModel):
    run_id: str = Field(min_length=1, max_length=128)
    release_id: str | None = Field(default=None, max_length=128)
    mode: str = "manual"


def _discover_release_id(
    meta: dict[str, Any],
    craftsman_run: dict[str, Any] | None,
) -> str | None:
    """If craftsman feedback has release_handoff but meta doesn't, persist it."""
    existing = (meta.get("publisher") or {}).get("release_id")
    if existing:
        return existing
    if not craftsman_run:
        return None
    feedback = craftsman_run.get("feedback")
    if not isinstance(feedback, dict):
        return None
    handoff = feedback.get("release_handoff")
    if not isinstance(handoff, dict):
        return None
    rid = handoff.get("release_id")
    if not rid and craftsman_run.get("run_id"):
        rid = f"rel-{craftsman_run['run_id']}"
    if rid:
        attach_release(meta["pipeline_id"], str(rid))
        return str(rid)
    return None


async def _fetch_snapshot(meta: dict[str, Any]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {"meta": meta}
    run_id = (meta.get("craftsman") or {}).get("run_id")
    release_id = (meta.get("publisher") or {}).get("release_id")
    craftsman_run: dict[str, Any] | None = None
    if run_id:
        try:
            craftsman_run = await craftsman_request("GET", f"/v1/runs/{run_id}")
            snapshot["craftsman_run"] = craftsman_run
        except HTTPException as exc:
            snapshot["craftsman_error"] = _format_http_error(exc)

    release_id = _discover_release_id(meta, craftsman_run) or release_id
    if release_id and "publisher_release" not in snapshot:
        try:
            snapshot["publisher_release"] = await craftsman_request(
                "GET", f"/v1/releases/{release_id}"
            )
        except HTTPException as exc:
            snapshot["publisher_error"] = _format_http_error(exc)

    events, next_line = read_hunter_events(meta["pipeline_id"])
    snapshot["hunter_events"] = events
    snapshot["hunter_next_after_line"] = next_line
    snapshot["workflow"] = derive_workflow(
        hunter_events=events,
        craftsman_run=craftsman_run,
        publisher_release=snapshot.get("publisher_release"),
        meta=meta,
    )
    return snapshot


def _format_http_error(exc: HTTPException) -> dict[str, Any]:
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    return {"status": exc.status_code, **detail}


@app.exception_handler(ValueError)
async def _value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": {"code": "invalid_input", "message": str(exc)}})


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "craftsman_reachable": await craftsman_health(),
        "craftsman_base_url": settings.craftsman_base_url,
        "version": app.version,
    }


@app.get("/api/pipelines")
async def list_pipelines(limit: int = Query(default=30, ge=1, le=200)) -> dict:
    return {"pipelines": list_pipeline_metas(limit=limit)}


@app.post("/api/pipelines/link-run")
async def link_run(body: LinkRunBody) -> dict:
    meta = upsert_meta_from_run(
        run_id=body.run_id,
        release_id=body.release_id,
        mode=body.mode,
    )
    return meta


@app.get("/api/pipelines/{pipeline_id}")
async def get_pipeline(pipeline_id: str) -> dict:
    meta = load_meta(pipeline_id)
    if meta is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "pipeline not found"})
    return await _fetch_snapshot(meta)


@app.get("/api/pipelines/{pipeline_id}/hunter/events")
async def hunter_events(
    pipeline_id: str,
    after_line: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict:
    if load_meta(pipeline_id) is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "pipeline not found"})
    events, next_after = read_hunter_events(pipeline_id, after_line=after_line, limit=limit)
    return {"pipeline_id": pipeline_id, "events": events, "next_after_line": next_after}


@app.get("/api/pipelines/{pipeline_id}/stream")
async def pipeline_stream(pipeline_id: str, request: Request) -> StreamingResponse:
    """SSE: tail hunter.jsonl + craftsman run/events + publisher status."""
    meta = load_meta(pipeline_id)
    if meta is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "pipeline not found"})

    async def generate():
        hunter_line = 0
        craftsman_after = 0
        run_id = (meta.get("craftsman") or {}).get("run_id")
        release_id = (meta.get("publisher") or {}).get("release_id")
        last_run_phase: str | None = None
        last_release_status: str | None = None
        tick = 0
        try:
            while True:
                if await request.is_disconnected():
                    break

                fresh_meta = load_meta(pipeline_id) or meta
                run_id = (fresh_meta.get("craftsman") or {}).get("run_id") or run_id
                release_id = (fresh_meta.get("publisher") or {}).get("release_id") or release_id

                events, hunter_line = read_hunter_events(
                    pipeline_id, after_line=hunter_line, limit=200
                )
                for row in events:
                    yield _sse("hunter", row)

                if run_id:
                    try:
                        run_row = await craftsman_request("GET", f"/v1/runs/{run_id}")
                        phase = str(run_row.get("phase") or "")
                        if phase != last_run_phase:
                            last_run_phase = phase
                            yield _sse("craftsman_run", run_row)
                        elif tick % 3 == 0:
                            yield _sse("craftsman_run", run_row)
                        new_release = _discover_release_id(fresh_meta, run_row)
                        if new_release and new_release != release_id:
                            release_id = new_release
                            yield _sse("release_discovered", {"release_id": release_id})
                        ev = await craftsman_request(
                            "GET",
                            f"/v1/runs/{run_id}/events",
                            params={"after_id": craftsman_after, "limit": 200},
                        )
                        for item in ev.get("events") or []:
                            yield _sse("craftsman", item)
                        craftsman_after = int(ev.get("next_after_id") or craftsman_after)
                    except HTTPException as exc:
                        yield _sse("craftsman_error", _format_http_error(exc))

                if release_id:
                    try:
                        rel = await craftsman_request("GET", f"/v1/releases/{release_id}")
                        status_key = (
                            str(rel.get("status") or ""),
                            str(rel.get("agent_c_status") or ""),
                        )
                        signature = "|".join(status_key)
                        if signature != last_release_status or tick % 3 == 0:
                            last_release_status = signature
                            yield _sse("publisher", rel)
                    except HTTPException as exc:
                        yield _sse("publisher_error", _format_http_error(exc))

                yield ":\n\n"  # keep-alive comment
                tick += 1
                await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            raise

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/craftsman/runs/{run_id}")
async def proxy_run(run_id: str) -> dict:
    return await craftsman_request("GET", f"/v1/runs/{run_id}")


@app.get("/api/craftsman/runs/{run_id}/events")
async def proxy_run_events(
    run_id: str,
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    return await craftsman_request(
        "GET",
        f"/v1/runs/{run_id}/events",
        params={"after_id": after_id, "limit": limit},
    )


@app.get("/api/craftsman/releases/{release_id}")
async def proxy_release(release_id: str) -> dict:
    return await craftsman_request("GET", f"/v1/releases/{release_id}")


@app.get("/api/artifacts/runs/{run_id}/{artifact_path:path}")
async def serve_artifact(run_id: str, artifact_path: str) -> FileResponse:
    path = await artifact_file(run_id, artifact_path)
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        media = "text/html; charset=utf-8"
    elif suffix == ".png":
        media = "image/png"
    elif suffix in {".jpg", ".jpeg"}:
        media = "image/jpeg"
    elif suffix == ".svg":
        media = "image/svg+xml"
    elif suffix == ".json":
        media = "application/json"
    else:
        media = "application/octet-stream"
    return FileResponse(path, media_type=media)


static_dir = settings.static_dir
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


def run() -> None:
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
