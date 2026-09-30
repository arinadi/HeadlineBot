"""All secrets travel as one .env file: uploaded as-is by the colab CLI, or
base64-encoded into the single HEADLINEBOT_ENV notebook secret."""
import base64

import pytest

import runner

WINDOWS_ENV = (
    "﻿# HeadlineBot secrets\r\n"
    "TELEGRAM_BOT_TOKEN=123:abc\r\n"
    "\r\n"
    "export TELEGRAM_CHAT_ID=-100123\r\n"
    'GEMINI_API_KEY="quoted value"\r\n'
    "OPENAI_COMPAT_API_KEY='sk-a=b=='\r\n"
    "  # indented comment\r\n"
    "not a setting\r\n"
)


def encode(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode()


def test_parse_env_reads_a_windows_saved_file():
    assert runner.parse_env(WINDOWS_ENV) == {
        "TELEGRAM_BOT_TOKEN": "123:abc",
        "TELEGRAM_CHAT_ID": "-100123",
        "GEMINI_API_KEY": "quoted value",
        "OPENAI_COMPAT_API_KEY": "sk-a=b==",
    }


def test_bundle_loads_every_key_and_reports_names():
    environ = {}
    loaded = runner.load_env_bundle(encode("A=1\nB=two\n"), environ)
    assert environ == {"A": "1", "B": "two"}
    assert sorted(loaded) == ["A", "B"]


def test_bundle_does_not_override_variables_already_set():
    environ = {"A": "from-notebook"}
    runner.load_env_bundle(encode("A=from-bundle\nB=2\n"), environ)
    assert environ == {"A": "from-notebook", "B": "2"}


def test_bundle_tolerates_whitespace_and_newlines_from_copy_paste():
    encoded = encode("A=1\n")
    environ = {}
    runner.load_env_bundle(f"  {encoded[:4]}\n{encoded[4:]}  \n", environ)
    assert environ == {"A": "1"}


@pytest.mark.parametrize("bad", ["not base64!!", base64.b64encode(b"\xff\xfe\x00bin").decode()])
def test_broken_bundle_error_names_the_secret(bad):
    with pytest.raises(ValueError, match="HEADLINEBOT_ENV"):
        runner.load_env_bundle(bad, {})
