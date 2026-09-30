"""VPS launcher: wake HeadlineBot on Colab when the chat needs it.

Runs forever on a small server (systemd, see deploy/). While no Colab VM is
running it long-polls Telegram; the first message from TELEGRAM_CHAT_ID starts
one with colab/colab-run.sh and is left unconfirmed, so the bot on Colab
receives and processes that same message. While a VM runs, or its state can't
be read, the launcher never polls: Telegram serves getUpdates to one consumer
per bot, and that must be the bot. After the bot's idle shutdown releases the
VM, the launcher listens again.

Standard library only, so it fits a 1 GB VPS next to the colab CLI.
    python3 launcher.py [--version prod|beta] [--gpu T4] [--session headlinebot]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from runner import parse_env

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
POLL_TIMEOUT = 50   # seconds Telegram holds a getUpdates call open
BUSY_RECHECK = 60   # seconds between `colab sessions` checks while a VM runs

# `colab sessions` prints one "[name] endpoint | Hardware: ..." line per VM.
_SESSION_LINE = re.compile(r"^\[(?P<name>[^\]]+)\] \S+ \| Hardware:", re.MULTILINE)


def log(message: str):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def session_state_from(output: str, session: str) -> bool | None:
    """True if `colab sessions` output lists our VM, False if it clearly doesn't,
    None if the output is not recognizable (errors): the caller treats that as busy."""
    names = {m.group("name") for m in _SESSION_LINE.finditer(output)}
    if session in names:
        return True
    if names or "No active sessions" in output:
        return False
    return None


class TelegramAPI:
    """The two Bot API calls the launcher needs. Never logs the URL (it holds the token)."""

    def __init__(self, token: str):
        self._base = f"https://api.telegram.org/bot{token}"

    def _call(self, method: str, params: dict, timeout: float):
        data = urllib.parse.urlencode(params).encode()
        with urllib.request.urlopen(f"{self._base}/{method}", data=data, timeout=timeout) as resp:
            body = json.load(resp)
        if not body.get("ok"):
            raise RuntimeError(f"Telegram {method}: {body.get('description')}")
        return body["result"]

    def get_updates(self, offset: int | None) -> list[dict]:
        params = {"timeout": POLL_TIMEOUT}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", params, timeout=POLL_TIMEOUT + 10)

    def send_message(self, chat_id: int, text: str):
        self._call("sendMessage", {"chat_id": chat_id, "text": text}, timeout=30)


class ColabCLI:
    """Runs the colab CLI and colab/colab-run.sh for one named session."""

    def __init__(self, session: str, gpu: str, version: str):
        self.session, self.gpu, self.version = session, gpu, version

    def session_state(self) -> bool | None:
        try:
            result = subprocess.run(["colab", "sessions"], capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as e:
            log(f"colab sessions failed: {e}")
            return None
        return session_state_from(result.stdout + result.stderr, self.session)

    def _run_script(self, *args: str, timeout: float) -> subprocess.CompletedProcess:
        script = os.path.join(REPO_DIR, "colab", "colab-run.sh")
        return subprocess.run(["bash", script, *args, "--session", self.session],
                              capture_output=True, text=True, timeout=timeout, cwd=REPO_DIR)

    def start(self) -> tuple[bool, str]:
        try:
            result = self._run_script("up", "--gpu", self.gpu, "--version", self.version, timeout=45 * 60)
            output = (result.stdout + result.stderr).strip()
            ok = result.returncode == 0
        except subprocess.TimeoutExpired:
            output, ok = "colab-run.sh up timed out after 45 minutes", False
        print(output, flush=True)  # into the journal; colab-run/bootstrap never print secret values
        if not ok:
            # A half-started VM would keep the launcher "busy" and burn quota: release it.
            try:
                self._run_script("stop", timeout=300)
            except subprocess.TimeoutExpired:
                log("colab-run.sh stop timed out")
        return ok, "\n".join(output.splitlines()[-5:])


def git_pull():
    """Wake with the latest code of the checked-out branch, like a notebook would."""
    try:
        result = subprocess.run(["git", "-C", REPO_DIR, "pull", "--ff-only", "-q"],
                                capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        log(f"git pull failed, waking with the current code: {e}")
        return
    if result.returncode != 0:
        log(f"git pull failed, waking with the current code: {result.stderr.strip()}")


class Launcher:
    def __init__(self, telegram, colab, chat_id: int, pull_code):
        self.telegram, self.colab = telegram, colab
        self.chat_id, self.pull_code = chat_id, pull_code
        self.offset: int | None = None

    def step(self) -> str:
        """One cycle: 'busy' (VM runs or unknown), 'idle', 'woke' or 'failed'."""
        if self.colab.session_state() is not False:
            return "busy"
        for update in self.telegram.get_updates(self.offset):
            update_id = update["update_id"]
            chat = (update.get("message") or {}).get("chat") or {}
            if chat.get("id") != self.chat_id:
                # Other chats and button presses: confirm and ignore.
                self.offset = update_id + 1
                continue
            # Leave this update unconfirmed so the bot on Colab receives it.
            self.offset = update_id
            self.telegram.send_message(self.chat_id, "⏰ Waking up HeadlineBot on Colab... (~2-3 min)")
            self.pull_code()
            ok, detail = self.colab.start()
            if ok:
                return "woke"
            self.telegram.send_message(self.chat_id, f"❌ Could not start Colab:\n{detail}")
            self.offset = update_id + 1  # skip it; the user can resend
            return "failed"
        return "idle"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Wake HeadlineBot on Colab when the chat needs it.")
    parser.add_argument("--version", choices=["prod", "beta"], default="prod")
    parser.add_argument("--gpu", default="T4")
    parser.add_argument("--session", default="headlinebot")
    parser.add_argument("--env", default=os.path.join(REPO_DIR, ".env"), help="path to the .env with the secrets")
    args = parser.parse_args(argv)

    with open(args.env, encoding="utf-8") as f:
        secrets = parse_env(f.read())
    token, chat_id = secrets.get("TELEGRAM_BOT_TOKEN"), secrets.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        sys.exit(f"TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in {args.env}")

    launcher = Launcher(TelegramAPI(token), ColabCLI(args.session, args.gpu, args.version), int(chat_id), git_pull)
    log(f"Launcher ready (session={args.session}, gpu={args.gpu}, version={args.version})")
    last = None
    while True:
        try:
            result = launcher.step()
        except (OSError, RuntimeError, ValueError) as e:
            # Network or Telegram hiccup (urllib errors are OSErrors): retry shortly.
            log(f"Error: {e}")
            time.sleep(15)
            continue
        if result != last:
            log(f"State: {result}")
            last = result
        if result == "busy":
            time.sleep(BUSY_RECHECK)


if __name__ == "__main__":
    main()
