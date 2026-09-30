#!/usr/bin/env bash
# colab-run.sh — run HeadlineBot on Google Colab via colab CLI. No git pull:
# the local checkout is tarred and uploaded, so the VM never touches git.
#
# Secrets: userdata.get() does NOT work in CLI sessions, so secrets travel
# as the local .env file (uploaded to the VM, never committed — .env is
# gitignored). Fill .env from .env.example. NEVER paste secret values into chat.
#
#   ./colab/colab-run.sh up [--session NAME] [--gpu T4] [--version prod|beta] [--cpu-deps]
#   ./colab/colab-run.sh logs [--session NAME] [--lines 50]
#   ./colab/colab-run.sh stop [--session NAME]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "${SCRIPT_DIR}")"
REPO_PARENT="$(dirname "${REPO_DIR}")"
REPO_BASE="$(basename "${REPO_DIR}")"
SESSION="headlinebot"
VERSION="prod"
DEPS="full"
GPU=""
LINES=50

usage() {
    sed -n '2,11p' "$0"
}

need_env() {
    if [ ! -f "${REPO_DIR}/.env" ]; then
        echo "missing ${REPO_DIR}/.env" >&2
        echo "copy .env.example to .env and fill it in" >&2
        echo "(.env is gitignored; values stay local)" >&2
        exit 1
    fi
}

cmd_up() {
    need_env
    command -v colab >/dev/null || { echo "colab CLI not found" >&2; exit 1; }

    local tarball="${SCRIPT_DIR}/hb.tar.gz"
    echo "[up] packing ${REPO_DIR} (code only)..."
    # --transform pins the top-level dir to HeadlineBot/ whatever the local
    # folder is named, so bootstrap.py always finds it. .env is uploaded
    # separately and must never ride inside the tarball; local job files,
    # caches and this script's own outputs don't belong on the VM either.
    tar -czf "${tarball}" --transform 's,^[^/]*,HeadlineBot,' \
        --exclude=.git --exclude=.env --exclude=.claude --exclude=__pycache__ \
        --exclude=.ruff_cache --exclude=.pytest_cache \
        --exclude=uploads --exclude=transcripts --exclude=edited_images \
        --exclude=hb.tar.gz --exclude=bootstrap.conf \
        -C "${REPO_PARENT}" "${REPO_BASE}"

    printf 'DEPS=%s\nVERSION=%s\n' "${DEPS}" "${VERSION}" > "${SCRIPT_DIR}/bootstrap.conf"

    echo "[up] creating session '${SESSION}'..."
    # shellcheck disable=SC2086
    colab new -s "${SESSION}" ${GPU} || echo "[up] session may already exist, continuing..."

    echo "[up] uploading code + .env + conf..."
    # Absolute paths: a relative remote path lands in the VM's filesystem root
    # (/), while bootstrap.py and `colab ls` look in /content.
    colab upload -s "${SESSION}" "${tarball}" /content/hb.tar.gz
    colab upload -s "${SESSION}" "${REPO_DIR}/.env" /content/.env
    colab upload -s "${SESSION}" "${SCRIPT_DIR}/bootstrap.conf" /content/bootstrap.conf

    echo "[up] bootstrapping on VM (pip install can take minutes)..."
    colab exec -s "${SESSION}" --timeout 1800 -f "${SCRIPT_DIR}/bootstrap.py"

    echo "[up] done. follow logs with: $0 logs --session ${SESSION}"
    echo "     release the VM with: $0 stop --session ${SESSION}"
}

cmd_logs() {
    # `colab exec` reads code only from -f FILE (it has no stdin "-" argument).
    local script
    script="$(mktemp --suffix=.py)"
    trap 'rm -f "${script}"' RETURN
    cat > "${script}" <<EOF
import os
found = None
for d in (os.getcwd(), "/content"):
    p = os.path.join(d, "hb-run", "bot.log")
    if os.path.isfile(p):
        found = p
        break
if found is None:
    print("--- no bot.log yet ---")
else:
    print("".join(open(found).readlines()[-${LINES}:]))
EOF
    colab exec -s "${SESSION}" --timeout 60 -f "${script}"
}

cmd_stop() {
    colab stop -s "${SESSION}"
}

# --- arg parsing ---
CMD="${1:-help}"
shift || true
while [ $# -gt 0 ]; do
    case "$1" in
        --session) SESSION="$2"; shift 2;;
        --gpu) GPU="--gpu $2"; shift 2;;
        --tpu) GPU="--tpu $2"; shift 2;;
        --version) VERSION="$2"; shift 2;;
        --cpu-deps) DEPS="cpu"; shift 1;;
        --lines) LINES="$2"; shift 2;;
        -h|--help|help) usage; exit 0;;
        *) echo "unknown arg: $1" >&2; usage; exit 1;;
    esac
done

case "${CMD}" in
    up) cmd_up;;
    logs) cmd_logs;;
    stop) cmd_stop;;
    *) usage; exit 1;;
esac
