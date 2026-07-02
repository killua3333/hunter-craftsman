from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PublisherPhase(StrEnum):
    VALIDATE = "validate"
    BUILD = "build"
    SIGN = "sign"
    UPLOAD = "upload"
    COMPLETE = "complete"
    FAILED = "failed"


class PublisherStatus(StrEnum):
    PREPARED = "prepared"
    BUILDING = "building"
    UPLOADING = "uploading"
    SUBMITTED = "submitted"
    INTERNAL_SUBMITTED = "internal_submitted"
    DRY_RUN_COMPLETE = "dry_run_complete"
    FAILED = "failed"


@dataclass
class ReleaseBuildResult:
    ok: bool
    aab_path: str | None = None
    apk_path: str | None = None
    log: str = ""
    reasons: list[str] = field(default_factory=list)
    dry_run: bool = False


@dataclass
class ReleaseUploadResult:
    ok: bool
    track: str = "internal"
    message: str = ""
    store_response: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False
