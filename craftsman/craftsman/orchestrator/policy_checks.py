from __future__ import annotations

from typing import Any

from craftsman.publisher.privacy_policy import is_placeholder_privacy_url


def check_release_compliance_metadata(release_handoff: dict[str, Any]) -> dict[str, Any]:
    metadata = release_handoff.get("compliance_metadata") or {}
    missing: list[str] = []

    required_fields = ("subtitle", "description", "keywords", "privacy_url")
    for field in required_fields:
        value = metadata.get(field)
        if field == "keywords":
            if not isinstance(value, list) or not value:
                missing.append("compliance_metadata.keywords")
            continue
        if not isinstance(value, str) or not value.strip():
            missing.append(f"compliance_metadata.{field}")

    privacy_url = str(metadata.get("privacy_url") or "").strip().lower()
    if privacy_url and not (privacy_url.startswith("http://") or privacy_url.startswith("https://")):
        missing.append("compliance_metadata.privacy_url_format")
    if privacy_url and is_placeholder_privacy_url(privacy_url):
        missing.append("compliance_metadata.privacy_url_placeholder")

    return {
        "passed": not missing,
        "issues": missing,
        "checked_fields": list(required_fields),
    }
