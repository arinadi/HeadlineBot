"""HeadlineBot Colab bootstrap — runs ON the Colab VM via `colab exec -f`.

CLI lifecycle: code arrives as hb.tar.gz (in-place, no git), secrets as the
local .env (uploaded; google.colab userdata does not work in CLI sessions).

Uploaded to /content by colab-run.sh:
  hb.tar.gz       repo snapshot (top-level dir: HeadlineBot/)
  .env            all secrets (never in git)
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


def main():
    tarball = find_file("hb.tar.gz")
    env_file = find_file(".env")
    conf_file = find_file("bootstrap.conf")

    # 1. Fresh extract (no git state, no leftovers).
    import shutil
    if os.path.exists(RUN_DIR):
        shutil.rmtree(RUN_DIR)
    os.makedirs(RUN_DIR)
    with tarfile.open(tarball, "r:gz") as tf:
        # filter="data" refuses absolute paths, "..", links out of RUN_DIR and
        # device files (Python 3.12+, which Colab runs).
        tf.extractall(RUN_DIR, filter="data")
    app_dir = os.path.join(RUN_DIR, "HeadlineBot")
    if not os.path.isdir(app_dir):
        raise SystemExit("extracted tree has no HeadlineBot/ dir")
    print(f"extracted to {app_dir}", flush=True)

    # 2. Load .env into the environment with the same parser runner.py uses
    #    (values stay in memory only, never printed).
    sys.path.insert(0, app_dir)
    from runner import parse_env
    with open(conf_file, encoding="utf-8") as f:
        conf = parse_env(f.read())
    deps = conf.get("DEPS", "full")
    version = conf.get("VERSION", "prod")
    with open(env_file, encoding="utf-8") as f:
        for key, val in parse_env(f.read()).items():
            os.environ.setdefault(key, val)
    os.environ["HEADLINEBOT_VERSION"] = version

    # 3. Verify critical secrets (names only, never values).
    missing = [k for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
               if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"missing secrets: {missing} (add them to your .env)")
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY not set - CPU transcription and LLM_PROVIDER=gemini unavailable", flush=True)

    # 4. Dependencies.
    req = "requirements_cpu.txt" if deps == "cpu" else "requirements.txt"
    print(f"installing {req}...", flush=True)
    rc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r", req],
        cwd=app_dir).returncode
    if rc != 0:
        raise SystemExit("pip install failed")

    # 5. Launch bot detached; exec returns while bot keeps polling.
    log = open(LOG_FILE, "a", buffering=1)
    proc = subprocess.Popen(
        [sys.executable, "start.py"],
        cwd=app_dir, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True)
    print(f"bot started pid={proc.pid} log={LOG_FILE}", flush=True)


if __name__ == "__main__":
    main()
