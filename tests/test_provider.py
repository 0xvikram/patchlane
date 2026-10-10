import json

import httpx2
import pytest

from backend.llm.provider import LLMNotConfigured, LLMProvider
from backend.settings import Config, LLMConfig, Settings


def _settings(**overrides) -> Settings:
    values = {"llm_base_url": "https://llm.test/v1", "llm_api_key": "k", "neatlogs_api_key": ""}
    return Settings.model_construct(**{**values, **overrides})


def _config(**models) -> Config:
    return Config(llm=LLMConfig(models=models, max_output_tokens=128))


def _completion(model: str, content: str | None, usage: dict | None = None) -> dict:
    body = {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
    }
    if usage:
        body["usage"] = usage
    return body


def _provider_with_fake_endpoint(config: Config, response_body: dict):
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json=response_body)

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return LLMProvider(_settings(), config, http_client=client), requests


async def test_chat_without_model_id_raises():
    provider = LLMProvider(_settings(), _config())
    with pytest.raises(LLMNotConfigured, match="light"):
        await provider.chat("light", [{"role": "user", "content": "hi"}])


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"llm_api_key": ""}, "LLM_API_KEY"),
        ({"llm_base_url": ""}, "LLM_BASE_URL"),
        ({"llm_api_key": "", "llm_base_url": ""}, "LLM_BASE_URL and LLM_API_KEY"),
    ],
)
async def test_chat_without_credentials_raises(overrides, expected):
    provider = LLMProvider(_settings(**overrides), _config(light="m-light"))
    with pytest.raises(LLMNotConfigured, match=expected):
        await provider.chat("light", [{"role": "user", "content": "hi"}])


async def test_chat_sends_role_model_and_returns_usage():
    provider, requests = _provider_with_fake_endpoint(
        _config(light="m-light"),
        _completion("m-light-2026", "ok", {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}),
    )

    result = await provider.chat("light", [{"role": "user", "content": "hi"}], max_tokens=20)

    sent = json.loads(requests[-1].content)
    assert str(requests[-1].url) == "https://llm.test/v1/chat/completions"
    assert sent["model"] == "m-light"
    assert sent["max_tokens"] == 20
    assert requests[-1].headers["authorization"] == "Bearer k"
    assert (result.text, result.model, result.prompt_tokens, result.completion_tokens) == ("ok", "m-light-2026", 7, 2)


async def test_chat_uses_config_token_limit_by_default():
    provider, requests = _provider_with_fake_endpoint(_config(coder="m-coder"), _completion("m", None))

    result = await provider.chat("coder", [{"role": "user", "content": "hi"}])

    assert json.loads(requests[-1].content)["max_tokens"] == 128
    assert (result.text, result.prompt_tokens, result.completion_tokens) == ("", 0, 0)
