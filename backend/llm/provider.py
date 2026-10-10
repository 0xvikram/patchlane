from pydantic import BaseModel

from backend.settings import Config, Role, Settings


class LLMNotConfigured(RuntimeError):
    pass


class ChatResult(BaseModel):
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int


class LLMProvider:
    def __init__(self, settings: Settings, config: Config, http_client=None):
        self._settings = settings
        self._config = config
        self._http_client = http_client
        self._client = None

    def model_for(self, role: Role) -> str:
        model = self._config.llm.models.get(role, "")
        if not model:
            raise LLMNotConfigured(f"No model id for role '{role}'. Set [llm.models] {role} in config.toml.")
        return model

    def _get_client(self):
        if self._client is None:
            missing = [
                name
                for name, value in (
                    ("LLM_BASE_URL", self._settings.llm_base_url),
                    ("LLM_API_KEY", self._settings.llm_api_key),
                )
                if not value
            ]
            if missing:
                raise LLMNotConfigured(f"Missing {' and '.join(missing)} in .env.")
            # Imported here so tracing can patch the library before first use.
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                base_url=self._settings.llm_base_url,
                api_key=self._settings.llm_api_key,
                timeout=self._config.llm.timeout_seconds,
                http_client=self._http_client,
            )
        return self._client

    async def chat(self, role: Role, messages: list[dict], max_tokens: int | None = None) -> ChatResult:
        model = self.model_for(role)
        client = self._get_client()
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens or self._config.llm.max_output_tokens,
        )
        usage = response.usage
        return ChatResult(
            text=response.choices[0].message.content or "",
            model=response.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )
