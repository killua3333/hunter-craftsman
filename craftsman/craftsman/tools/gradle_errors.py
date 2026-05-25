from __future__ import annotations

import re
from typing import Any

_KOTLIN_ERROR_RE = re.compile(
    r"^e:\s*file:///(.+?):(\d+):(\d+)\s*(.+)$",
    re.MULTILINE,
)
_JAVA_ERROR_RE = re.compile(
    r"^(.+\.java):(\d+):\s*error:\s*(.+)$",
    re.MULTILINE,
)
_TASK_FAILED_RE = re.compile(
    r"Execution failed for task '([^']+)'",
    re.MULTILINE,
)


def parse_gradle_errors(log: str, *, tail_lines: int = 80) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()

    for pattern, default_category in (
        (_KOTLIN_ERROR_RE, "kotlin_compile_error"),
        (_JAVA_ERROR_RE, "java_compile_error"),
    ):
        for m in pattern.finditer(log):
            key = m.group(0)
            if key in seen:
                continue
            seen.add(key)
            msg = m.group(3) if pattern is _JAVA_ERROR_RE else m.group(4)
            category = default_category
            if "Unresolved reference" in msg:
                category = "undefined_symbol"
            elif "Cannot find a parameter" in msg or "No value passed" in msg:
                category = "parameter_error"
            errors.append(
                {
                    "file": m.group(1),
                    "line": int(m.group(2)),
                    "column": int(m.group(3)) if pattern is _KOTLIN_ERROR_RE else None,
                    "message": msg.strip(),
                    "category": category,
                }
            )

    task_failures = _TASK_FAILED_RE.findall(log)
    lines = log.splitlines()
    raw_tail = "\n".join(lines[-tail_lines:]) if lines else ""
    return {
        "errors": errors[:50],
        "error_count": len(errors),
        "task_failures": task_failures[:10],
        "raw_tail": raw_tail,
    }
