from backend.settings import Settings

_started = False


def init_tracing(settings: Settings, workflow_name: str, tags: list[str] | None = None) -> bool:
    """Start neatlogs. Returns True when traces are being exported.

    Must run before `openai` is imported: auto-instrumentation patches the library at init time.
    """
    global _started
    if not settings.neatlogs_api_key:
        return False
    if _started:
        return True
    import neatlogs

    neatlogs.init(
        api_key=settings.neatlogs_api_key,
        workflow_name=workflow_name,
        instrumentations=["openai"],
        tags=tags or [],
    )
    _started = True
    return True


def shutdown_tracing() -> None:
    global _started
    if not _started:
        return
    import neatlogs

    neatlogs.flush(timeout_millis=10_000)
    neatlogs.shutdown(timeout_millis=10_000)
    _started = False
