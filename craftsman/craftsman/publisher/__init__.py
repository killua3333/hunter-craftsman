"""Agent C: Android packaging, signing, and Play Store release."""

__all__ = ["run_android_release"]


def __getattr__(name: str):
    if name == "run_android_release":
        from craftsman.publisher.orchestrator import run_android_release

        return run_android_release
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
