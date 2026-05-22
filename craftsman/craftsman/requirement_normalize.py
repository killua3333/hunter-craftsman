"""实现前规范化 requirement（不删字段）。"""

from __future__ import annotations

import copy
import re
from typing import Any

_NAV_VIEW = re.compile(r"\bNavigationView\b")


def _rewrite_strings(value: Any) -> Any:
    if isinstance(value, str):
        return _NAV_VIEW.sub("NavigationStack", value)
    if isinstance(value, list):
        return [_rewrite_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_strings(val) for key, val in value.items()}
    return value


def normalize_requirement(req: dict[str, Any]) -> dict[str, Any]:
    """保留全部字段；将文案中的 NavigationView 统一为 NavigationStack。"""
    out = copy.deepcopy(req)
    return _rewrite_strings(out)
