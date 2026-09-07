import os
import subprocess
import sys
import time
import urllib.request


def detect_platform():
    """Detect runtime: Kaggle, Colab, or Local.

    NOTE: Intentional duplicate of headlinebot.utils.detect_platform.
    runner.py must work before the repo is cloned (headlinebot/ may not exist),
    so it cannot import from headlinebot here. Keep logic in sync.
    """
    try:
        from kaggle_secrets import UserSecretsClient  # noqa: F401
        return "kaggle"
    except ImportError:
        pass
    try:
        from google.colab import userdata  # noqa: F401
        return "colab"
    except ImportError:
        pass
    return "local"

# Force unbuffered output (critical for Kaggle)
os.environ['PYTHONUNBUFFERED'] = '1'

# --- CONFIGURATION ---
REPO_URL = "https://github.com/arinadi/HeadlineBot.git"
REPO_NAME = "HeadlineBot"
# ---------------------

# Version → Branch mapping
VERSION_BRANCH_MAP = {
    "prod": "main",
    "beta": "beta",
}
DEFAULT_VERSION = "prod"

def redact(cmd: str) -> str:
    """Redact embedded tokens from log lines (https://user:token@host)."""
    import re
    return re.sub(r"https://[^@\s]+@", "https://***@", cmd)


def run_command(cmd, *, _sensitive: bool = False):
    """Run shell command via os.system. Logs redacted command. Prefer run_list()."""
    print(f"Executing: {redact(cmd) if _sensitive else cmd}", flush=True)
    return os.system(cmd)


def run_list(args: list, *, sensitive: bool = False, env: dict | None = None):
    """Run argv list without shell (no ps token leak). Logs redacted argv."""
    shown = " ".join(redact(a) if sensitive else a for a in args)
    print(f"Executing: {shown}", flush=True)
    import subprocess as _sp
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return _sp.call(args, env=merged)

def run_command_streaming(cmd):
    """Run command with real-time streaming output (important for Kaggle)."""
    print(f"Executing: {cmd}", flush=True)
    process = subprocess.Popen(
        cmd, shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True
    )
    for line in process.stdout:
        print(line, end='', flush=True)
    process.wait()
    return process.returncode


def is_repo_checkout():
    """True when cwd already IS the repo (CLI lifecycle: code uploaded,
    no setup needed). Otherwise the web lifecycle applies (clone/update)."""
    return (
        os.path.isfile("start.py")
        and os.path.isfile("main.py")
        and os.path.isfile(os.path.join("headlinebot", "__init__.py"))
    )


def resolve_version():
    """Resolve HEADLINEBOT_VERSION env var to branch name."""
    version = os.environ.get("HEADLINEBOT_VERSION", DEFAULT_VERSION).lower().strip()
    if version not in VERSION_BRANCH_MAP:
        print(f"⚠️ Unknown version '{version}'. Available: {list(VERSION_BRANCH_MAP.keys())}. Using 'prod'.", flush=True)
        version = DEFAULT_VERSION
    branch = VERSION_BRANCH_MAP[version]
    return version, branch

def load_secrets(platform):
    """Load secrets into os.environ via Infisical (or platform-native fallback)."""
    from headlinebot.secrets import load_all_secrets
    return load_all_secrets(platform=platform)

def verify_secrets(platform):
    """Verify critical secrets are loaded."""
    required = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']
    missing = [k for k in required if not os.environ.get(k)]

    if missing:
        print(f"\n❌ CRITICAL: Missing secrets: {', '.join(missing)}", flush=True)
        if os.environ.get("INFISICAL_PROJECT_ID"):
            print("   → Check that secrets exist in Infisical dashboard for your project/env.", flush=True)
        elif platform == "kaggle":
            print("   → Go to: Add-ons → Secrets → Attach INFISICAL_CLIENT_ID & INFISICAL_CLIENT_SECRET", flush=True)
            print("   → Or set INFISICAL_PROJECT_ID env var to use Infisical.", flush=True)
        elif platform == "colab":
            print("   → Go to: Secrets tab (🔑) → Add INFISICAL_CLIENT_ID & INFISICAL_CLIENT_SECRET", flush=True)
            print("   → Or set INFISICAL_PROJECT_ID env var to use Infisical.", flush=True)
        return False

    optional = ['GEMINI_API_KEY']
    for key in optional:
        if not os.environ.get(key):
            print(f"  ⚠️ {key} not set — AI features (summary/retouch/photo) will be disabled.", flush=True)

    return True

def download_repo_fallback(branch):
    """Download repo as ZIP when git is unavailable (fallback for Kaggle)."""
    import io
    import zipfile
    from pathlib import PurePosixPath

    zip_url = f"https://github.com/arinadi/HeadlineBot/archive/refs/heads/{branch}.zip"
    print(f"📥 Downloading repo ({branch} branch) from {zip_url}...", flush=True)
    try:
        req = urllib.request.Request(zip_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            zip_data = resp.read()

        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            # Validate members before extract (Zip Slip hardening, trusted origin but still)
            for info in zf.infolist():
                p = PurePosixPath(info.filename)
                if p.is_absolute() or ".." in p.parts:
                    raise ValueError(f"Unsafe path in repo ZIP: {info.filename!r}")
            zf.extractall(".")

        # Rename extracted folder (GitHub zip extracts to RepoName-branch)
        extracted = os.path.join(".", f"{REPO_NAME}-{branch}")
        if os.path.exists(extracted):
            if os.path.exists(REPO_NAME):
                import shutil
                shutil.rmtree(REPO_NAME)
            os.rename(extracted, REPO_NAME)

        os.chdir(REPO_NAME)
        return True
    except Exception as e:
        print(f"❌ Download failed: {e}", flush=True)
        return False

def set_version_env(version, branch):
    """Set version-related environment variables for the bot."""
    os.environ['HEADLINEBOT_VERSION'] = version
    os.environ['HEADLINEBOT_BRANCH'] = branch

    # Per-version defaults (can be overridden by user env vars)
    if version == "beta":
        os.environ.setdefault('ENABLE_IDLE_MONITOR', 'True')
        os.environ.setdefault('IDLE_SHUTDOWN_MINUTES', '5')
    else:  # prod
        os.environ.setdefault('ENABLE_IDLE_MONITOR', 'True')
        os.environ.setdefault('IDLE_SHUTDOWN_MINUTES', '10')

def main():
    start_time = time.time()
    if 'INIT_START' not in os.environ:
        os.environ['INIT_START'] = str(int(start_time))

    platform = detect_platform()
    version, branch = resolve_version()

    print(f"🔄 Platform: {platform.upper()}", flush=True)
    print(f"🔄 Version: {version.upper()} (branch: {branch})", flush=True)
    print("🔄 Checking environment...", flush=True)

    # Set version env vars
    set_version_env(version, branch)

    # 1. Load Secrets (skip if already loaded from notebook cell)
    if not os.environ.get('SECRETS_LOADED'):
        load_secrets(platform)
    else:
        print("🔑 Secrets already loaded from notebook cell", flush=True)

    # 2. Verify critical secrets
    if not verify_secrets(platform):
        sys.exit(1)

    # 3. Code lifecycle:
    #    - IN-PLACE (colab-CLI): cwd already is the repo (uploaded), run here.
    #    - SETUP (web notebook): empty VM, clone or update the repo first.
    # NOTE: IN-PLACE intentionally skips git, so --version switch is ignored there.
    # Log current sha when available to make mismatch visible.
    if is_repo_checkout():
        print("🔄 Lifecycle: IN-PLACE (repo already here, skipping git)...", flush=True)
        try:
            _sha = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            if _sha:
                print(f"   Local HEAD: {_sha} (requested version: {version}/{branch})", flush=True)
        except Exception:
            print(f"   Requested version: {version}/{branch} (no git sha available)", flush=True)
    elif os.path.exists(".git"):
        print(f"⏳ Updating current directory (branch: {branch})...", flush=True)
        run_list(["git", "fetch", "--depth", "1", "origin", branch])
        run_list(["git", "reset", "--hard", f"origin/{branch}"])
    elif os.path.exists(REPO_NAME):
        print(f"⏳ Entering and updating {REPO_NAME} (branch: {branch})...", flush=True)
        os.chdir(REPO_NAME)
        run_list(["git", "fetch", "--depth", "1", "origin", branch])
        run_list(["git", "reset", "--hard", f"origin/{branch}"])
    else:
        print(f"⏳ Cloning {REPO_NAME} (branch: {branch})...", flush=True)
        token = os.environ.get('GITHUB_TOKEN')
        # Never embed token in URL (ps/logs/.git/config leak). Use transient header.
        git_env = None
        if token:
            import base64
            cred = base64.b64encode(f"x-access-token:{token}".encode()).decode()
            header = f"Authorization: Basic {cred}"
            git_env = {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "http.extraHeader",
                "GIT_CONFIG_VALUE_0": header,
            }

        rc = run_list(["git", "clone", "--depth", "1", "--branch", branch, REPO_URL, REPO_NAME],
                      sensitive=bool(token), env=git_env)
        if rc != 0:
            print("⚠️ Git clone failed. Trying direct download...", flush=True)
            if not download_repo_fallback(branch):
                sys.exit("❌ Failed to obtain repository")
        else:
            os.chdir(REPO_NAME)
            # Defense-in-depth: ensure stored origin has no credentials.
            try:
                subprocess.run(["git", "remote", "set-url", "origin", REPO_URL],
                               capture_output=True, timeout=10)
            except Exception:
                pass

    print(f"✅ Code ready ({int(time.time()) - int(os.environ['INIT_START'])}s) [{version}]", flush=True)

    # 4. Install Core Dependencies
    print("⏳ Installing core dependencies...", flush=True)
    if run_command("pip install -r requirements_cpu.txt -q") != 0:
        print("❌ Failed to install core dependencies", flush=True)
        sys.exit(1)
    print(f"✅ Core dependencies ready ({int(time.time()) - int(os.environ['INIT_START'])}s)", flush=True)

    # 5. Run the Bot (streaming for Kaggle)
    print(f"🚀 Starting HeadlineBot [{version.upper()}]...", flush=True)
    if platform == "kaggle":
        run_command_streaming("python start.py")
    else:
        run_command("python start.py")

if __name__ == "__main__":
    main()
