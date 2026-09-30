"""AI provider for summary, retouch and photo analysis (LLM_PROVIDER).

  gemini        — Gemini/Gemma through google-genai, using the discovered model chains.
  openai_compat — any OpenAI-compatible Chat Completions API (e.g. OpenCode Go);
                  models are tried in the configured order.

Both expose `await generate(task, system, text, image_jpeg=None, temperature, session)`,
which returns the model's text or raises RuntimeError once every model has failed.
Transcription does not go through here (Whisper, or the Gemini File API).
"""
import base64
from urllib.parse import urlparse

from headlinebot import config
from headlinebot.model_manager import try_model_chain
from headlinebot.utils import get_model_chain, log

USER_AGENT = "HeadlineBot/1.0"


class GeminiLLM:
    """Gemini/Gemma via google-genai."""

    name = "gemini"

    def __init__(self, client):
        self.client = client

    async def generate(self, task: str, system: str, text: str, image_jpeg: bytes | None = None,
                       temperature: float = 0.3, session: str | None = None) -> str:
        from google.genai import types  # lazy: large SDK, only needed with this provider

        if image_jpeg is None:
            chain = get_model_chain(task)
            contents = [system, text]
            gen_config = types.GenerateContentConfig(temperature=temperature)
        else:
            # Image input goes to the configured Gemma model; the discovered chains
            # are text chains and include models that can't see images.
            chain = {"all": [config.GEMMA_MODEL]}
            contents = [types.Part.from_bytes(data=image_jpeg, mime_type="image/jpeg"), text]
            gen_config = types.GenerateContentConfig(system_instruction=system, temperature=temperature)

        response = await try_model_chain(self.client, chain, contents, config=gen_config, task_name=task)
        if response and response.text:
            return response.text
        raise RuntimeError(f"All models failed for {task}")


class OpenAICompatLLM:
    """Any OpenAI-compatible Chat Completions API; `client` is an openai.AsyncOpenAI."""

    name = "openai_compat"

    def __init__(self, client, models: list[str], vision_models: list[str], session_header: bool = False):
        self.client = client
        self.models = models
        self.vision_models = vision_models
        self.session_header = session_header

    async def generate(self, task: str, system: str, text: str, image_jpeg: bytes | None = None,
                       temperature: float = 0.3, session: str | None = None) -> str:
        import openai  # lazy: only needed with this provider

        if image_jpeg is None:
            models, user_content = self.models, text
        else:
            image_url = "data:image/jpeg;base64," + base64.b64encode(image_jpeg).decode()
            models = self.vision_models
            user_content = [{"type": "text", "text": text},
                            {"type": "image_url", "image_url": {"url": image_url}}]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user_content}]
        headers = {"x-opencode-session": session} if self.session_header and session else None

        failures = []
        for model in models:
            try:
                log("MODEL", f"Trying {model} for {task}...")
                response = await self.client.chat.completions.create(
                    model=model, messages=messages, temperature=temperature, extra_headers=headers)
            except openai.OpenAIError as e:
                # The SDK already retried transient errors; move on to the next model.
                log("MODEL", f"{model} failed for {task}: {e}")
                failures.append(f"{model}: {e}")
                continue
            content = response.choices[0].message.content if response.choices else None
            if content:
                log("MODEL", f"Success with {model} for {task}")
                return content
            log("MODEL", f"{model} returned an empty answer for {task}")
            failures.append(f"{model}: empty answer")
        raise RuntimeError(f"All models failed for {task}: {'; '.join(failures)}")


def build_llm(provider: str, gemini_client, base_url: str | None, api_key: str | None,
              models: list[str], vision_models: list[str], http_client=None):
    """Create the provider named by LLM_PROVIDER.

    Returns None for gemini without a Gemini client (no GEMINI_API_KEY): AI features
    are then simply unavailable. Raises ValueError for a misconfigured provider.
    """
    if provider == "gemini":
        return GeminiLLM(gemini_client) if gemini_client else None
    if provider != "openai_compat":
        raise ValueError(f"Unknown LLM_PROVIDER {provider!r}: use 'gemini' or 'openai_compat'")

    missing = [name for name, value in (("OPENAI_COMPAT_BASE_URL", base_url), ("OPENAI_COMPAT_API_KEY", api_key),
                                        ("OPENAI_COMPAT_MODELS", models),
                                        ("OPENAI_COMPAT_VISION_MODELS", vision_models)) if not value]
    if missing:
        raise ValueError(f"LLM_PROVIDER=openai_compat needs {', '.join(missing)}")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=base_url, http_client=http_client,
                         # OpenCode asks API clients to identify themselves.
                         default_headers={"User-Agent": USER_AGENT})
    # OpenCode Go rejects requests without a per-conversation x-opencode-session;
    # other providers don't need it.
    host = urlparse(base_url).hostname or ""
    session_header = host == "opencode.ai" or host.endswith(".opencode.ai")
    return OpenAICompatLLM(client, models, vision_models, session_header=session_header)
