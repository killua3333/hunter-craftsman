from __future__ import annotations

import re
from typing import Any

_ERROR_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*error:\s*(?P<message>.+)$",
    re.MULTILINE,
)
_UNDEFINED_RE = re.compile(r"Cannot find '([^']+)' in scope")


def parse_xcode_errors(log: str, *, tail_lines: int = 80) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _ERROR_RE.finditer(log):
        key = m.group(0)
        if key in seen:
            continue
        seen.add(key)
        msg = m.group("message")
        category = "compile_error"
        um = _UNDEFINED_RE.search(msg)
        if um:
            category = "undefined_symbol"
        errors.append(
            {
                "file": m.group("file"),
                "line": int(m.group("line")),
                "column": int(m.group("col")),
                "message": msg,
                "category": category,
            }
        )
    lines = log.splitlines()
    raw_tail = "\n".join(lines[-tail_lines:]) if lines else ""
    return {
        "errors": errors[:50],
        "error_count": len(errors),
        "warnings_count": log.count(": warning:"),
        "raw_tail": raw_tail,
    }
