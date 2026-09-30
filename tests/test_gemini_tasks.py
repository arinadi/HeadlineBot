"""A Gemini failure must surface as an error, never as text that gets saved and
sent as if it were the transcript or summary. Uploaded audio must not be left
on Gemini's servers."""
import asyncio

import pytest

from headlinebot.utils import summarize_text, transcribe_with_gemini
from tests.fakes import FakeGeminiClient


def test_transcription_returns_model_text():
    client = FakeGeminiClient(["Halo semua."])
    text, _ = asyncio.run(transcribe_with_gemini("audio.m4a", client))
    assert text == "Halo semua."


def test_transcription_raises_when_upload_fails():
    client = FakeGeminiClient(upload_error=RuntimeError("upload refused"))
    with pytest.raises(Exception, match="upload refused"):
        asyncio.run(transcribe_with_gemini("audio.m4a", client))


def test_transcription_raises_when_every_model_fails():
    client = FakeGeminiClient([RuntimeError("bad request")] * 5)
    with pytest.raises(RuntimeError, match="All models failed"):
        asyncio.run(transcribe_with_gemini("audio.m4a", client))


def test_uploaded_audio_is_deleted_after_success():
    client = FakeGeminiClient(["Halo semua."])
    asyncio.run(transcribe_with_gemini("audio.m4a", client))
    assert client.files.deleted == ["files/abc123"]


def test_uploaded_audio_is_deleted_when_transcription_fails():
    client = FakeGeminiClient([RuntimeError("bad request")] * 5)
    with pytest.raises(RuntimeError, match="All models failed"):
        asyncio.run(transcribe_with_gemini("audio.m4a", client))
    assert client.files.deleted == ["files/abc123"]


def test_summary_raises_when_every_model_fails():
    client = FakeGeminiClient([RuntimeError("bad request")] * 5)
    with pytest.raises(RuntimeError, match="All models failed"):
        asyncio.run(summarize_text("transkrip", client))
