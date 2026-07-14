import os
import subprocess
import sys
import time
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

from headlinebot.utils import detect_platform

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

    # 1. Load Secrets (skip if already loaded from notebook cell)
    if not os.environ.get('SECRETS_LOADED'):
        load_secrets(platform)
    else:
        print("🔑 Secrets already loaded from notebook cell", flush=True)

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
