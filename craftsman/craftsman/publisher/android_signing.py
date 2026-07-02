from __future__ import annotations

import shutil
from pathlib import Path

from craftsman.config import settings
from craftsman.secrets import resolve_secret_path, resolve_secret_value


def write_keystore_properties(project_dir: Path) -> tuple[bool, str]:
    """
    Copy keystore into project dir and write keystore.properties.
    Returns (configured, message).
    """
    store_path = resolve_secret_path("ANDROID_KEYSTORE_PATH", settings.android_keystore_path)
    store_password = resolve_secret_value("ANDROID_KEYSTORE_PASSWORD", settings.android_keystore_password)
    key_alias = resolve_secret_value("ANDROID_KEY_ALIAS", settings.android_key_alias)
    key_password = resolve_secret_value("ANDROID_KEY_PASSWORD", settings.android_key_password)

    if not all([store_path, store_password, key_alias, key_password]):
        return False, "signing secrets not configured; using debug/unsigned build path"

    keystore_path = Path(store_path)
    if not keystore_path.is_file():
        return False, f"keystore file not found: {store_path}"

    # Copy keystore into project so Docker can access it
    dest = project_dir / "app" / "release.keystore"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(keystore_path, dest)

    # Write keystore.properties at project root; rootProject.file() in app/build.gradle.kts finds it.
    # file("release.keystore") in app/ context resolves to app/release.keystore.
    props = project_dir / "keystore.properties"
    props.write_text(
        "\n".join(
            [
                "storeFile=release.keystore",
                f"storePassword={store_password}",
                f"keyAlias={key_alias}",
                f"keyPassword={key_password}",
            ]
        ),
        encoding="utf-8",
    )
    return True, "release signing configured via keystore.properties"


def cleanup_keystore_properties(project_dir: Path) -> None:
    """Delete keystore.properties and copied keystore after build."""
    for d in (project_dir, project_dir / "app"):
        props = d / "keystore.properties"
        if props.is_file():
            props.unlink(missing_ok=True)
        keystore = d / "release.keystore"
        if keystore.is_file():
            keystore.unlink(missing_ok=True)


def signing_configured() -> bool:
    path = resolve_secret_path("ANDROID_KEYSTORE_PATH", settings.android_keystore_path)
    return bool(path and path.is_file())
