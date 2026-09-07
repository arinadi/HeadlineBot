"""HeadlineBot Colab bootstrap — runs ON the Colab VM via `colab exec -f`.

CLI lifecycle: code arrives as hb.tar.gz (in-place, no git), secrets as
.env (uploaded, local-only). Forces platform="local" so secrets come from
os.environ — never from google.colab userdata (broken in CLI mode) or
Kaggle secrets.

Uploaded alongside this file by colab-run.sh:
  hb.tar.gz       repo snapshot (top-level dir: HeadlineBot/)
  .env            local-only secrets (INFISICAL_* + overrides, never in git)
  bootstrap.conf  DEPS=full|cpu, VERSION=prod|beta
"""
import os
import subprocess
import sys
import tarfile

SEARCH_DIRS = [os.getcwd(), "/content", os.path.expanduser("~")]
RUN_DIR = os.path.join(os.getcwd(), "hb-run")
LOG_FILE = os.path.join(RUN_DIR, "bot.log")


def find_file(name):
    for d in SEARCH_DIRS:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(f"{name} not found (searched: {SEARCH_DIRS})")


def parse_kv_file(path):
    """Minimal KEY=VALUE parser (no dotenv dependency). Never prints values."""
    data = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if key:
                data[key] = val
    return data


def main():
    tarball = find_file("hb.tar.gz")
    env_file = find_file(".env")
    conf_file = find_file("bootstrap.conf")

    conf = parse_kv_file(conf_file)
    deps = conf.get("DEPS", "full")
    version = conf.get("VERSION", "prod")

    # 1. Fresh extract (no git state, no leftovers).
    import shutil
    if os.path.exists(RUN_DIR):
        shutil.rmtree(RUN_DIR)
    os.makedirs(RUN_DIR)
    with tarfile.open(tarball, "r:gz") as tf:
        # Use data filter when available (3.12+), fallback otherwise.
        try:
            if hasattr(tarfile, "data_filter"):
                tf.extractall(RUN_DIR, filter="data")
            else:
                tf.extractall(RUN_DIR)
        except TypeError:
            # Older Python without filter= kwarg
            tf.extractall(RUN_DIR)
    app_dir = os.path.join(RUN_DIR, "HeadlineBot")
    if not os.path.isdir(app_dir):
        raise SystemExit("extracted tree has no HeadlineBot/ dir")
    print(f"extracted to {app_dir}", flush=True)

    # 2. Load .env into environment (values stay in memory only).
    for key, val in parse_kv_file(env_file).items():
        os.environ.setdefault(key, val)
    os.environ["HEADLINEBOT_VERSION"] = version

    # 3. Pull real secrets from Infisical (platform forced to local:
    #    userdata.get() does not work in CLI-driven sessions).
    sys.path.insert(0, app_dir)
    from headlinebot.secrets import load_infisical_secrets
    load_infisical_secrets(platform="local")

    # 4. Verify critical secrets (names only, never values).
    missing = [k for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
               if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"missing secrets: {missing} "
                         "(check Infisical project/env)")
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY not set - AI features disabled", flush=True)

    # 5. Dependencies.
    req = "requirements_cpu.txt" if deps == "cpu" else "requirements.txt"
    print(f"installing {req}...", flush=True)
    rc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r", req],
        cwd=app_dir).returncode
    if rc != 0:
        raise SystemExit("pip install failed")

    # 6. Launch bot detached; exec returns while bot keeps polling.
    log = open(LOG_FILE, "a", buffering=1)
    proc = subprocess.Popen(
        [sys.executable, "start.py"],
        cwd=app_dir, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True)
    print(f"bot started pid={proc.pid} log={LOG_FILE}", flush=True)


if __name__ == "__main__":
    main()
