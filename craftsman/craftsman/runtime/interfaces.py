from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class BuildResult:
    ok: bool
    mode: str
    exit_code: int
    log: str = ""
    reasons: list[str] = field(default_factory=list)


class ExecutionBackend(Protocol):
    """Execution backend contract for Craftsman implementation phase."""

    @property
    def mode(self) -> str:
        """Human-readable backend mode, e.g. demo|macos_xcode|android_gradle."""

    def can_compile(self) -> bool:
        """Whether backend supports native compile/build verification."""

    def compile(self, project_dir: Path, scheme: str) -> BuildResult:
        """Compile project and return structured result."""

    def platform_note(self) -> str:
        """Return runtime platform summary for feedback."""


@dataclass
class ReleasePrepareResult:
    ok: bool
    release_id: str | None = None
    message: str = "release backend not implemented"


class ReleaseBackend(Protocol):
    """Reserved protocol for future release agent integration."""

    def prepare(self, handoff: dict[str, Any]) -> ReleasePrepareResult:
        """Prepare release job from handoff payload."""

    def submit(self, release_id: str) -> dict[str, Any]:
        """Submit prepared release to store."""

    def status(self, release_id: str) -> dict[str, Any]:
        """Fetch release status."""
