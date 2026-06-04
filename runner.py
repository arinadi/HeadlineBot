import os
import sys
import time
import subprocess
import urllib.request

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

def run_command(cmd):
    print(f"Executing: {cmd}", flush=True)
    return os.system(cmd)

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

def detect_platform():
    """Detect runtime: Kaggle, Colab, or Local."""
    try:
        from kaggle_secrets import UserSecretsClient
        return "kaggle"
    except ImportError:
        pass
    try:
        from google.colab import userdata
        return "colab"
    except ImportError:
        pass
    return "local"

def resolve_version():
    """Resolve HEADLINEBOT_VERSION env var to branch name."""
    version = os.environ.get("HEADLINEBOT_VERSION", DEFAULT_VERSION).lower().strip()
    if version not in VERSION_BRANCH_MAP:
        print(f"⚠️ Unknown version '{version}'. Available: {list(VERSION_BRANCH_MAP.keys())}. Using 'prod'.", flush=True)
        version = DEFAULT_VERSION
    branch = VERSION_BRANCH_MAP[version]
    return version, branch

def load_secrets(platform):
    """Load secrets into os.environ from platform-specific source."""
    secret_keys = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'GEMINI_API_KEY', 'GITHUB_TOKEN', 'HF_TOKEN']

    if platform == "kaggle":
        print("🔑 Loading secrets from Kaggle...", flush=True)
        from kaggle_secrets import UserSecretsClient
        client = UserSecretsClient()
        loaded = 0
        for key in secret_keys:
            try:
                val = client.get_secret(key)
                if val:
                    os.environ[key] = str(val)
                    loaded += 1
                    print(f"  ✅ {key}", flush=True)
            except Exception:
                pass
        if loaded == 0:
            print("  ⚠️ No secrets found! Go to Add-ons → Secrets → Attach keys.", flush=True)
        return loaded

    elif platform == "colab":
        print("🔑 Loading secrets from Colab...", flush=True)
        from google.colab import userdata
        loaded = 0
        for key in secret_keys:
            try:
                val = userdata.get(key)
                if val:
                    os.environ[key] = str(val)
                    loaded += 1
                    print(f"  ✅ {key}", flush=True)
            except Exception:
                pass
        return loaded
    else:
        print("🔑 Using environment variables (local mode)", flush=True)
        return -1

def verify_secrets(platform):
    """Verify critical secrets are loaded."""
    required = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']
    missing = [k for k in required if not os.environ.get(k)]

    if missing:
        print(f"\n❌ CRITICAL: Missing secrets: {', '.join(missing)}", flush=True)
        if platform == "kaggle":
            print("   → Go to: Add-ons → Secrets → Attach TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID", flush=True)
        elif platform == "colab":
            print("   → Go to: Secrets tab (🔑) → Add TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID", flush=True)
        return False

    optional = ['GEMINI_API_KEY']
    for key in optional:
        if not os.environ.get(key):
            print(f"  ⚠️ {key} not set — AI features (summary/retouch/photo) will be disabled.", flush=True)

    return True

def download_repo_fallback(branch):
    """Download repo as ZIP when git is unavailable (fallback for Kaggle)."""
    import zipfile
    import io

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
    print(f"🔄 Checking environment...", flush=True)

    # Set version env vars
    set_version_env(version, branch)

    # 1. Load Secrets
    loaded = load_secrets(platform)

    # 2. Verify critical secrets
    if not verify_secrets(platform):
        sys.exit(1)

    # 3. Clone or Update Repository (branch-aware)
    if os.path.exists(".git"):
        print(f"⏳ Updating current directory (branch: {branch})...", flush=True)
        run_command(f"git fetch --depth 1 origin {branch}")
        run_command(f"git reset --hard origin/{branch}")
    elif os.path.exists(REPO_NAME):
        print(f"⏳ Entering and updating {REPO_NAME} (branch: {branch})...", flush=True)
        os.chdir(REPO_NAME)
        run_command(f"git fetch --depth 1 origin {branch}")
        run_command(f"git reset --hard origin/{branch}")
    else:
        print(f"⏳ Cloning {REPO_NAME} (branch: {branch})...", flush=True)
        token = os.environ.get('GITHUB_TOKEN')
        clone_url = REPO_URL
        if token and "github.com" in clone_url:
            clone_url = clone_url.replace("https://", f"https://{token}@")

        rc = run_command(f"git clone --depth 1 --branch {branch} {clone_url}")
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
