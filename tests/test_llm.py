"""The AI provider (LLM_PROVIDER) behind summary, retouch and photo analysis.

openai_compat tries its models in order and only fails when all of them do.
Requests identify as HeadlineBot, and OpenCode gets the per-job session header
it requires (x-opencode-session).
"""
import asyncio
import base64

import httpx2
import openai
import pytest

from headlinebot.llm import OpenAICompatLLM, build_llm
from headlinebot.utils import retouch_transcript, summarize_text
from tests.fakes import FakeOpenAIClient

COMPAT = {"api_key": "key", "models": ["m1", "m2"], "vision_models": ["v1"]}


def compat(replies, **kwargs):
    client = FakeOpenAIClient(replies)
    return OpenAICompatLLM(client, models=["m1", "m2"], vision_models=["v1"], **kwargs), client.chat.completions


def generate(llm, **kwargs):
    args = {"task": "summary", "system": "SYS", "text": "TEXT"} | kwargs
    return asyncio.run(llm.generate(**args))


def test_first_model_gets_system_prompt_and_text():
    llm, completions = compat(["ringkasan"])
    assert generate(llm) == "ringkasan"
    call = completions.calls[0]
    assert call["model"] == "m1"
    assert call["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "TEXT"}]


def test_next_model_is_tried_when_one_errors():
    llm, completions = compat([openai.OpenAIError("down"), "ok"])
    assert generate(llm) == "ok"
    assert [c["model"] for c in completions.calls] == ["m1", "m2"]


def test_empty_answer_counts_as_a_failure():
    llm, _ = compat(["", "ok"])
    assert generate(llm) == "ok"


def test_raises_when_every_model_fails():
    llm, _ = compat([openai.OpenAIError("down")] * 2)
    with pytest.raises(RuntimeError, match="All models failed for summary"):
        generate(llm)


def test_image_goes_to_vision_models_as_jpeg_data_uri():
    llm, completions = compat(["DAYLIGHT"])
    generate(llm, task="photo", image_jpeg=b"\xff\xd8jpeg")
    call = completions.calls[0]
    assert call["model"] == "v1"
    parts = call["messages"][1]["content"]
    assert {"type": "text", "text": "TEXT"} in parts
    expected_url = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8jpeg").decode()
    assert {"type": "image_url", "image_url": {"url": expected_url}} in parts


def capture_requests(base_url):
    """build_llm with a real SDK client whose HTTP transport records requests."""
    seen = []

    def handler(request):
        seen.append(request)
        return httpx2.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "m1",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}],
        })

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    llm = build_llm("openai_compat", gemini_client=None, base_url=base_url, http_client=http_client, **COMPAT)
    return llm, seen


def test_opencode_requests_carry_user_agent_and_job_session():
    llm, seen = capture_requests("https://opencode.ai/zen/go/v1")
    generate(llm, session="job-123")
    assert seen[0].url.path.endswith("/chat/completions")
    assert seen[0].headers["user-agent"].startswith("HeadlineBot")
    assert seen[0].headers["x-opencode-session"] == "job-123"


def test_other_hosts_get_no_opencode_session_header():
    llm, seen = capture_requests("https://api.example.com/v1")
    generate(llm, session="job-123")
    assert seen[0].headers["user-agent"].startswith("HeadlineBot")
    assert "x-opencode-session" not in seen[0].headers


def test_openai_compat_without_api_key_is_rejected():
    with pytest.raises(ValueError, match="OPENAI_COMPAT_API_KEY"):
        build_llm("openai_compat", gemini_client=None, base_url="https://x/v1",
                  api_key=None, models=["m1"], vision_models=["v1"])


def test_openai_compat_without_models_is_rejected():
    with pytest.raises(ValueError, match="OPENAI_COMPAT_MODELS"):
        build_llm("openai_compat", gemini_client=None, base_url="https://x/v1",
                  api_key="key", models=[], vision_models=["v1"])


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        build_llm("claude", gemini_client=None, base_url=None, api_key=None, models=[], vision_models=[])


def test_gemini_provider_is_unavailable_without_a_gemini_client():
    assert build_llm("gemini", gemini_client=None, base_url=None, api_key=None, models=[], vision_models=[]) is None


class RecordingLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def test_summary_uses_the_journalist_prompt_and_job_session():
    llm = RecordingLLM("RINGKASAN")
    assert asyncio.run(summarize_text("transkrip", llm, session="job-1")) == "RINGKASAN"
    call = llm.calls[0]
    assert "FAKTA BERITA" in call["system"] and call["text"] == "transkrip"
    assert call["session"] == "job-1"


def test_retouch_falls_back_to_the_original_transcript_on_failure():
    llm = RecordingLLM(RuntimeError("All models failed for retouch"))
    assert asyncio.run(retouch_transcript("transkrip asli", llm)) == "transkrip asli"
