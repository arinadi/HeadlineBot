import os
import time
import sys

# --- CONFIGURATION ---
REPO_URL = "https://github.com/arinadi/TTB.git" 
REPO_NAME = "TTB"
# ---------------------

def run_command(cmd):
    print(f"Executing: {cmd}")
    return os.system(cmd)

def main():
    start_time = time.time()
    if 'INIT_START' not in os.environ:
        os.environ['INIT_START'] = str(int(start_time))

    print("🔄 Checking environment...")

    # 1. Clone or Update Repository
    if os.path.exists(".git"):
        # We are already inside a git repo, assume it's the right one
        print(f"⏳ Updating current directory...")
        run_command("git fetch --depth 1 origin")
        run_command("git reset --hard origin/main")
    elif os.path.exists(REPO_NAME):
        # Repo exists as a subdirectory
        print(f"⏳ Entering and updating {REPO_NAME}...")
        os.chdir(REPO_NAME)
        run_command("git fetch --depth 1 origin")
        run_command("git reset --hard origin/main")
    else:
        # Need to clone
        print(f"⏳ Cloning {REPO_NAME}...")
        token = os.environ.get('GITHUB_TOKEN')
        clone_url = REPO_URL
        if token and "github.com" in clone_url:
            clone_url = clone_url.replace("https://", f"https://{token}@")
        
        run_command(f"git clone --depth 1 {clone_url}")
        os.chdir(REPO_NAME)
        
    print(f"✅ Code ready ({int(time.time()) - int(os.environ['INIT_START'])}s)")

    # 2. Install Dependencies (using uv for speed)
    print("⏳ Installing dependencies with uv...")
    if run_command("bash setup_uv.sh") != 0:
        print("❌ Failed to install dependencies")
        sys.exit(1)
    print(f"✅ Dependencies installed ({int(time.time()) - int(os.environ['INIT_START'])}s)")

    # 3. Run the Bot
    print("🚀 Starting TTB...")
    run_command("python start.py")

if __name__ == "__main__":
    main()
