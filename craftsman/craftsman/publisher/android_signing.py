from __future__ import annotations

from pathlib import Path

from craftsman.config import settings
from craftsman.secrets import resolve_secret_value


def write_keystore_properties(project_dir: Path) -> tuple[bool, str]:
    """
    Write keystore.properties for Gradle signing if secrets are configured.
    Returns (configured, message).
    """
    store_file = resolve_secret_value("ANDROID_KEYSTORE_PATH", None)
    store_password = resolve_secret_value("ANDROID_KEYSTORE_PASSWORD", None)
    key_alias = resolve_secret_value("ANDROID_KEY_ALIAS", None)
    key_password = resolve_secret_value("ANDROID_KEY_PASSWORD", None)

    if not all([store_file, store_password, key_alias, key_password]):
        return False, "signing secrets not configured; using debug/unsigned build path"

    keystore_path = Path(store_file)
    if not keystore_path.is_file():
        return False, f"keystore file not found: {store_file}"

    props = project_dir / "keystore.properties"
    props.write_text(
        "\n".join(
            [
                f"storeFile={keystore_path.as_posix()}",
                f"storePassword={store_password}",
                f"keyAlias={key_alias}",
                f"keyPassword={key_password}",
            ]
        ),
        encoding="utf-8",
    )
    return True, "release signing configured via keystore.properties"


def cleanup_keystore_properties(project_dir: Path) -> None:
    """Delete keystore.properties after build to avoid plaintext secrets on disk."""
    props = project_dir / "keystore.properties"
    if props.is_file():
        props.unlink(missing_ok=True)


def signing_configured() -> bool:
    return bool(resolve_secret_value("ANDROID_KEYSTORE_PATH", None))
