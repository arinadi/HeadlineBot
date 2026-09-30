import base64
import binascii
import os
import subprocess
import sys
import time
import urllib.request


def detect_platform():
    """Detect runtime: Kaggle, Colab, or Local."""
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

def parse_env(text: str) -> dict[str, str]:
    """Parse .env text into {KEY: VALUE}.

    Handles what a hand-edited file on Windows or Linux contains: a UTF-8 BOM,
    CRLF, blank lines, '#' comments, `export ` prefixes and quoted values. Only the
    first '=' splits, since API keys and base64 values often contain '='.
    Shared by colab/bootstrap.py so both launch paths read .env the same way.
    """
    env = {}
    for line in text.lstrip("\ufeff").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            env[key] = value
    return env


def load_env_bundle(encoded: str, environ=None) -> list[str]:
    """Load a base64-encoded .env (the HEADLINEBOT_ENV notebook secret) into environ.

    Variables already set win, so a value set in the notebook overrides the bundle.
    Returns the names loaded (never the values, which are secrets).
    """
    environ = os.environ if environ is None else environ
    try:
        # Copy-paste can wrap or pad the value; base64 itself has no whitespace.
        text = base64.b64decode("".join(encoded.split()), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as e:
        raise ValueError(f"HEADLINEBOT_ENV is not a base64-encoded .env file ({e})") from e
    loaded = []
    for key, value in parse_env(text).items():
        if key not in environ:
            environ[key] = value
            loaded.append(key)
    return loaded


def run_command(cmd):
    print(f"Executing: {cmd}", flush=True)
    return os.system(cmd)

def run_git(*args):
    """Run git without a shell (the repo is public, so no credentials are involved)."""
    print(f"Executing: git {' '.join(args)}", flush=True)
    return subprocess.call(["git", *args])

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

def verify_secrets(platform):
    """Verify critical secrets are loaded."""
    required = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']
    missing = [k for k in required if not os.environ.get(k)]

    if missing:
        print(f"\n❌ CRITICAL: Missing secrets: {', '.join(missing)}", flush=True)
        where = {"kaggle": "Add-ons → Secrets", "colab": "Secrets tab (🔑)"}.get(platform, "the environment")
        print(f"   → Put them in your .env, then store base64 of it as HEADLINEBOT_ENV in {where}"
              " (README: Secrets).", flush=True)
        return False

    optional = ['GEMINI_API_KEY']
    for key in optional:
        if not os.environ.get(key):
            print(f"  ⚠️ {key} not set — CPU-mode transcription and LLM_PROVIDER=gemini are unavailable.", flush=True)

    return True

def download_repo_fallback(branch):
    """Download repo as ZIP when git is unavailable (fallback for Kaggle)."""
    import io
    import zipfile

    zip_url = f"https://github.com/arinadi/HeadlineBot/archive/refs/heads/{branch}.zip"
    print(f"📥 Downloading repo ({branch} branch) from {zip_url}...", flush=True)
    try:
        req = urllib.request.Request(zip_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            zip_data = resp.read()

        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
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

    # 1. Load secrets from the HEADLINEBOT_ENV bundle the notebook cell passed in
    bundle = os.environ.get('HEADLINEBOT_ENV')
    if bundle:
        try:
            loaded = load_env_bundle(bundle)
        except ValueError as e:
            sys.exit(f"❌ {e}")
        print(f"🔑 Loaded {len(loaded)} secrets from HEADLINEBOT_ENV: {', '.join(sorted(loaded))}", flush=True)

    # 2. Verify critical secrets
    if not verify_secrets(platform):
        sys.exit(1)

    # 3. Code lifecycle:
    #    - IN-PLACE (colab-CLI): cwd already is the repo (uploaded), run here.
    #    - SETUP (web notebook): empty VM, clone or update the repo first.
    if is_repo_checkout():
        print("🔄 Lifecycle: IN-PLACE (repo already here, skipping git)...", flush=True)
    elif os.path.exists(".git"):
        print(f"⏳ Updating current directory (branch: {branch})...", flush=True)
        run_git("fetch", "--depth", "1", "origin", branch)
        run_git("reset", "--hard", f"origin/{branch}")
    elif os.path.exists(REPO_NAME):
        print(f"⏳ Entering and updating {REPO_NAME} (branch: {branch})...", flush=True)
        os.chdir(REPO_NAME)
        run_git("fetch", "--depth", "1", "origin", branch)
        run_git("reset", "--hard", f"origin/{branch}")
    else:
        print(f"⏳ Cloning {REPO_NAME} (branch: {branch})...", flush=True)
        rc = run_git("clone", "--depth", "1", "--branch", branch, REPO_URL, REPO_NAME)
        if rc != 0:
            print("⚠️ Git clone failed. Trying direct download...", flush=True)
            if not download_repo_fallback(branch):
                sys.exit("❌ Failed to obtain repository")
        else:
            os.chdir(REPO_NAME)

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
