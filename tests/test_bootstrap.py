"""colab/bootstrap.py on the VM: extract the uploaded code, load the uploaded
.env with runner.parse_env, install the chosen requirements, start the bot."""
import io
import os
import runpy
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    """What colab-run.sh uploads to /content, with a Windows-saved .env."""
    with tarfile.open(tmp_path / "hb.tar.gz", "w:gz") as tar:
        tar.add(REPO / "runner.py", arcname="HeadlineBot/runner.py")
        data = b"print('bot')\n"
        info = tarfile.TarInfo("HeadlineBot/start.py")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    (tmp_path / "bootstrap.conf").write_bytes(b"DEPS=cpu\r\nVERSION=beta\r\n")
    (tmp_path / ".env").write_bytes(
        b"\xef\xbb\xbfTELEGRAM_BOT_TOKEN=1:x\r\nexport TELEGRAM_CHAT_ID=-100\r\nOPENAI_COMPAT_API_KEY='k=='\r\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run_bootstrap(monkeypatch):
    environ, calls = {}, []
    monkeypatch.setattr(os, "environ", environ)
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: calls.append(("run", args, kw)) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: calls.append(("popen", args, kw)) or SimpleNamespace(pid=1))
    runpy.run_path(str(REPO / "colab" / "bootstrap.py"), run_name="__main__")
    return environ, calls


def test_loads_env_and_version(uploads, monkeypatch):
    environ, _ = run_bootstrap(monkeypatch)
    assert environ["TELEGRAM_BOT_TOKEN"] == "1:x"
    assert environ["TELEGRAM_CHAT_ID"] == "-100"
    assert environ["OPENAI_COMPAT_API_KEY"] == "k=="
    assert environ["HEADLINEBOT_VERSION"] == "beta"


def test_installs_chosen_requirements_then_starts_the_bot(uploads, monkeypatch):
    _, calls = run_bootstrap(monkeypatch)
    app_dir = str(uploads / "hb-run" / "HeadlineBot")
    (kind, pip_args, pip_kw), (kind2, bot_args, bot_kw) = calls
    assert kind == "run" and pip_args[-1] == "requirements_cpu.txt" and pip_kw["cwd"] == app_dir
    assert kind2 == "popen" and bot_args[-1] == "start.py" and bot_kw["cwd"] == app_dir


def test_stops_when_telegram_secrets_are_missing(uploads, monkeypatch):
    (uploads / ".env").write_text("GEMINI_API_KEY=x\n")
    with pytest.raises(SystemExit, match="TELEGRAM_BOT_TOKEN"):
        run_bootstrap(monkeypatch)
