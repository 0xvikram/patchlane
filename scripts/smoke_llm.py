"""Make one traced model call. Run: uv run python -m scripts.smoke_llm"""

import asyncio
import sys

from backend.settings import get_settings, load_config
from backend.tracing import init_tracing, shutdown_tracing


async def main() -> int:
    settings = get_settings()
    tracing = init_tracing(settings, workflow_name="patchlane-smoke", tags=["smoke"])
    print(f"neatlogs tracing: {'on' if tracing else 'off (NEATLOGS_API_KEY is empty)'}")

    from backend.llm.provider import LLMNotConfigured, LLMProvider

    provider = LLMProvider(settings, load_config())
    try:
        result = await provider.chat(
            "light",
            [{"role": "user", "content": "Reply with exactly: patchlane online"}],
            max_tokens=512,
        )
    except LLMNotConfigured as exc:
        print(f"Not configured: {exc}")
        return 2
    finally:
        shutdown_tracing()

    print(f"model: {result.model}")
    print(f"reply: {result.text.strip()}")
    print(f"tokens: {result.prompt_tokens} in, {result.completion_tokens} out")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
