from backend import tracing
from backend.settings import Settings


def test_tracing_is_off_without_a_key():
    settings = Settings.model_construct(llm_base_url="", llm_api_key="", neatlogs_api_key="")
    assert tracing.init_tracing(settings, workflow_name="t") is False
    tracing.shutdown_tracing()
