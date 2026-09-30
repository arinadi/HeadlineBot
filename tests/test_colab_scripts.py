"""colab/colab-run.sh on Linux, against a fake `colab` that records its calls,
and the real colab CLI's interface that the scripts and launcher depend on.

colab upload puts relative remote paths in the VM's filesystem root, so every
upload must target /content/...; colab exec only reads code from -f FILE.
"""
import inspect
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

import launcher

REPO = Path(__file__).resolve().parent.parent
SESSION = "headlinebot"

linux_bash = pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None,
                                reason="colab-run.sh targets Linux/macOS bash")

FAKE_COLAB = """#!/usr/bin/env bash
echo "colab $*" >> "$FAKE_LOG"
if [ "$1" = exec ]; then
    for arg in "$@"; do [ -f "$arg" ] && cat "$arg" >> "$FAKE_LOG"; done
fi
"""


@pytest.fixture
def checkout(tmp_path):
    """A minimal copy of the repo layout colab-run.sh packs and uploads."""
    repo = tmp_path / "TTB"
    (repo / "colab").mkdir(parents=True)
    for name in ("colab-run.sh", "bootstrap.py"):
        shutil.copy(REPO / "colab" / name, repo / "colab" / name)
    (repo / "main.py").write_text("print('bot')\n")
    (repo / ".env").write_text("TELEGRAM_BOT_TOKEN=fake\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "colab"
    fake.write_text(FAKE_COLAB)
    fake.chmod(0o755)
    return repo, bin_dir, tmp_path / "calls.log"


def run_script(checkout, *args):
    repo, bin_dir, log = checkout
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "FAKE_LOG": str(log), "HOME": str(repo.parent)}
    result = subprocess.run(["bash", str(repo / "colab" / "colab-run.sh"), *args],
                            capture_output=True, text=True, env=env, timeout=120)
    calls = log.read_text() if log.exists() else ""
    return result, calls


@linux_bash
def test_up_uploads_to_content_and_runs_bootstrap(checkout):
    repo = checkout[0]
    result, calls = run_script(checkout, "up", "--gpu", "T4", "--version", "beta")
    assert result.returncode == 0, result.stderr
    assert f"colab new -s {SESSION} --gpu T4" in calls
    assert f"colab upload -s {SESSION} {repo}/colab/hb.tar.gz /content/hb.tar.gz" in calls
    assert f"colab upload -s {SESSION} {repo}/.env /content/.env" in calls
    assert f"colab upload -s {SESSION} {repo}/colab/bootstrap.conf /content/bootstrap.conf" in calls
    assert f"colab exec -s {SESSION} --timeout 1800 -f {repo}/colab/bootstrap.py" in calls
    assert "VERSION=beta" in (repo / "colab" / "bootstrap.conf").read_text()


@linux_bash
def test_up_packs_code_under_headlinebot_without_secrets(checkout):
    repo = checkout[0]
    run_script(checkout, "up")
    with tarfile.open(repo / "colab" / "hb.tar.gz") as tar:
        names = tar.getnames()
    assert "HeadlineBot/main.py" in names
    assert all(name.startswith("HeadlineBot") for name in names)
    assert not any(name.endswith(("/.env", "hb.tar.gz", "bootstrap.conf")) for name in names)


@linux_bash
def test_logs_runs_its_snippet_from_a_file(checkout):
    result, calls = run_script(checkout, "logs", "--lines", "7")
    assert result.returncode == 0, result.stderr
    assert f"colab exec -s {SESSION} --timeout 60 -f " in calls
    assert "hb-run" in calls and "[-7:]" in calls


@linux_bash
def test_up_refuses_to_run_without_env(checkout):
    (checkout[0] / ".env").unlink()
    result, calls = run_script(checkout, "up")
    assert result.returncode != 0
    assert "missing" in result.stderr and calls == ""


# --- The real colab CLI (installed in CI's colab-cli job; skipped elsewhere) ---

# CI's colab-cli job sets REQUIRE_COLAB_CLI so a failed install fails instead of skipping.
needs_colab = pytest.mark.skipif(shutil.which("colab") is None and not os.environ.get("REQUIRE_COLAB_CLI"),
                                 reason="colab CLI not installed")


@needs_colab
@pytest.mark.parametrize("command, flags", [
    ("new", ["--session", "--gpu"]),
    ("upload", ["--session"]),
    ("exec", ["--session", "--file", "-f", "--timeout"]),
    ("stop", ["--session"]),
    ("sessions", []),
])
def test_real_cli_has_the_flags_the_scripts_use(command, flags):
    # The CLI's rich help is colored on GitHub Actions; color codes split "--session".
    env = {k: v for k, v in os.environ.items() if k != "FORCE_COLOR"} | {"NO_COLOR": "1", "TERM": "dumb"}
    result = subprocess.run(["colab", command, "--help"], capture_output=True, text=True, timeout=120, env=env)
    assert result.returncode == 0, result.stderr
    help_text = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    for flag in flags:
        assert flag in help_text, f"colab {command} lost {flag}"


@needs_colab
def test_launcher_understands_real_session_listing_output():
    from colab_cli.commands import session

    line = session._format_session_line(name=SESSION, endpoint="e", accelerator="T4", variant="GPU")
    assert launcher.session_state_from(line, SESSION) is True
    assert "No active sessions found on server." in inspect.getsource(session.sessions_command)
    assert launcher.session_state_from("[colab] No active sessions found on server.", SESSION) is False
