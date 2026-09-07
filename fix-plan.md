# Fix Plan — chore/audit-fixes (P0 + P1 + P2 hygiene)

Base: `main`. Branch: `chore/audit-fixes`. Source findings: `report.md` Phase 1 (F1–F5) + Phase 2 (C/S/L/E/D).
Policy: English only. No secrets in logs. No commit/push in this plan phase unless separately approved.

## Goal

Make advertised features actually work and close exploitable paths, without adding new features:
- Fix broken wiring (presets, Gradio, CPU boot, idle timers, Gemini readiness).
- Close authz/secret/archive/error-handling P0s.
- Follow with P1 reliability and P2 hygiene (pins, CI, ignore, docs, defaults).

## Non-goals

- No new features (no `/help`, `/retry`, dashboard, DB, new models).
- No credential rotation, no live Colab/Kaggle repro with real secrets.
- No `git commit`, `git push`, PR creation (requires separate approval).
- No dependency upgrades beyond pinning; no behavior redesign beyond documented fixes.

## Execution order (smallest-risk first, stop after each group and re-verify)

### Group A — P0 wiring (must land together or not at all)

#### A1. Presets path + locks single source
- Problem: `headlinebot/image_editor.py:32` expects `headlinebot/docs/presets.json` (missing); real file is root `presets.json`. `PORTRAIT l [-8,-15]` reversed. JSON locks diverge from `CORRECT_PROMPT_TEMPLATE` hardcoded locks (`image_editor.py:127-131`).
- Files: `headlinebot/image_editor.py`, `presets.json` (move to `headlinebot/presets.json` or fix `_PRESETS_PATH`), `headlinebot/config.py` if GEMMA/JPEG centralized.
- Steps: move file, fix `_PRESETS_PATH`, fix `PORTRAIT` to `[-15,-8]`, generate prompt lock text from JSON, add import-time assert (16 presets, non-empty BACKLIGHT).
- Verify: `python -c "from headlinebot.image_editor import _PRESETS_DATA; assert len(_PRESETS_DATA['presets'])==16"`; `python -m ruff check headlinebot/image_editor.py`; manual `_get_preset("BACKLIGHT")` non-empty.

#### A2. Gemini readiness gate (C1)
- Problem: `main.py:142-145` pre-sets `models_ready_event` in GEMINI mode before `gemini_client` + `discover_models()` (`main.py:360-369`). Worker writes error-string as transcript (`headlinebot/utils.py:227-228` → `main.py:571-596`).
- Files: `main.py`, `headlinebot/utils.py`.
- Steps: remove import-time pre-set; set event only after client + discovery succeed/fail with fallback; in worker, if `gemini_client is None`, mark job `failed` instead of writing error text to `TS_*.txt`.
- Verify: `rg -n "models_ready_event" main.py`; static review that no `TS_*` write path accepts error-string; `compileall`.

#### A3. Gradio import + single launch + shutdown (F2, C5)
- Problem: `main.py:230,272` `import gradio_handler` always fails; `gradio_handler=None` shadow (`main.py:43`); double `create_task(initialize_gradio_background())` (`main.py:377` + `818-819`); `shutdown_gradio()` never called; `process_upload` fire-and-forget lies (`headlinebot/gradio_handler.py:85`).
- Files: `main.py`, `headlinebot/gradio_handler.py`.
- Steps: fix import to `from headlinebot import gradio_handler`; keep single launch site; wire `shutdown_gradio()` into `perform_shutdown()`; fix `message_id=0` reply-to handling; surface Future errors to Gradio status; validate `_main_loop.is_running()`.
- Verify: with `gradio` installed, `GRADIO_AVAILABLE` true, no double bind in logs; `rg -n "shutdown_gradio|initialize_gradio_background" main.py headlinebot/gradio_handler.py`.

#### A4. CPU boot import-safe + requirements_cpu (F3)
- Problem: `main.py:23` top-level `edit_image` pulls `cv2/numpy/PIL` (`image_editor.py:17-19`); `secrets.py:19` needs `requests`; CPU requirements lack all of them.
- Files: `main.py`, `requirements_cpu.txt`, `headlinebot/gradio_handler.py` (gradio dep note).
- Steps: lazy-import `edit_image` inside `_process_image_job()`; add `requests`, `google-genai`, `Pillow`, `numpy`, `opencv-python-headless` to CPU file OR explicitly document CPU-no-photo mode with clear log; keep `requirements.txt` full.
- Verify: fresh venv `pip install -r requirements_cpu.txt` then `python -c "import main"` succeeds (without GPU deps if no-photo mode, else with added deps).

#### A5. Idle timers single source (F4)
- Problem: `main.py:68-70,824-827` mutates aliases; `IdleMonitor` reads `Config.*` (`bot_classes.py:90,149,182-195`). Multiplier no-op.
- Files: `main.py`, `headlinebot/bot_classes.py`.
- Steps: remove alias mutation; add `IdleMonitor.set_effective_timeouts()` or compute timeouts before construction at `main.py:860-862`; log effective values once.
- Verify: `rg -n "IDLE_.*MINUTES" main.py headlinebot/bot_classes.py headlinebot/config.py`; GEMINI-mode log matches actual monitor behavior.

### Group B — P0 security / safety (land before any public testing)

#### B1. Callback authz (S1)
- Problem: `CallbackQueryHandler(button_callback)` at `main.py:872` has no `chat_filter`; `button_callback` (`main.py:748-786`) allows `shutdown_bot`/`cancel_*`/`extend_idle` with no sender check, no confirm.
- Files: `main.py`.
- Steps: add `filters=chat_filter` or manual `query.message.chat_id != TELEGRAM_CHAT_ID` deny; log `from_user.id` on shutdown/cancel; add confirm step for `shutdown_bot`.
- Verify: `rg -n "CallbackQueryHandler|chat_filter" main.py`; static review of all `query.data` branches for auth check.

#### B2. Token redaction + subprocess hygiene (F5/S2)
- Problem: `runner.py:188-193` embeds `GITHUB_TOKEN` in URL, `run_command()` logs full cmd (`runner.py:38,43`), `shell=True` + `os.system` exposes token in logs/`ps`; branch interpolated into shell.
- Files: `runner.py`.
- Steps: list-form `subprocess.run`, token via `GIT_HTTP_EXTRAHEADER`, `redact()` helper for logs, no token in `Executing:` output.
- Verify: `rg -n "os\.system|shell=True|clone_url|GITHUB_TOKEN" runner.py`; manual log grep shows no token pattern.

#### B3. Archive validation (S4)
- Problem: `ZipFile.extractall` without member checks (`bot_classes.py:439-446`, `runner.py:117-118`); `tarfile.extractall` without filter (`colab/bootstrap.py:63-64`). Telegram ZIP is attacker-reachable.
- Files: `headlinebot/bot_classes.py`, `runner.py`, `colab/bootstrap.py`.
- Steps: reject absolute/`..`/symlink entries, enforce total-size cap, use `filter="data"` for tar with 3.10 fallback.
- Verify: unit test with malicious names (`../evil`, `/abs`, symlink) rejected; `rg -n "extractall|ZipFile|tarfile"`.

#### B4. Error-handler shutdown scope (E1/E2)
- Problem: `global_error_handler` (`main.py:880-926`) treats `Forbidden` as transient, ignores `RetryAfter` delay, and calls `perform_shutdown` on any non-transient per-update error (single bad filename can kill bot).
- Files: `main.py`.
- Steps: `Forbidden` → fatal path; honor `retry_after`; timestamped transient window; remove default `perform_shutdown` from per-update path (shutdown only on init allowlist / N-in-M criticals).
- Verify: `rg -n "RetryAfter|Forbidden|perform_shutdown" main.py`; review handler branches.

### Group C — P1 reliability (after B green)

#### C1. Secrets + config single source (F6/F10/S6)
- Files: `runner.py`, `headlinebot/utils.py`, `headlinebot/config.py`, `headlinebot/image_editor.py`, `headlinebot/gradio_handler.py`, `headlinebot/secrets.py`.
- Steps: dedupe `detect_platform()` (keep in `utils`, import in `runner`); centralize `GEMMA_MODEL`/`JPEG_QUALITY`/`TELEGRAM_CHAT_ID` in `Config`; replace stale aliases in `main.py:49-70` with use-site `Config.*` or `reload()` after secrets load; cache Infisical credentials, log source (never values).
- Verify: single `def detect_platform`; `rg -n "GEMMA_MODEL|JPEG_QUALITY|TELEGRAM_CHAT_ID"`.

#### C2. Job model + cancel semantics (F7/C3)
- Files: `headlinebot/bot_classes.py`, `main.py`, `headlinebot/gradio_handler.py`.
- Steps: `author_display_name="Unknown"` default, `_original_message=None`, `Literal["transcript","image"]`, `Job.from_parts()` to remove fake-message hack (`bot_classes.py:302-311`); `cancel_job` returns False for processing; UI text fix; Gradio `message_id=None` handling.
- Verify: `python -m ruff check`, `compileall`, review `reply_photo` paths unified.

#### C3. Startup/GPU/download integrity (L1/L3, C4 teardown)
- Files: `start.py`, `main.py`, `headlinebot/bot_classes.py`, `colab/bootstrap.py`.
- Steps: decide WHISPER only if `nvidia-smi` AND `torch.cuda`; verify Whisper file sizes/checksums, edge-triggered progress logs; idempotent shutdown (event, cancel tasks, PTB stop order, `shutdown_gradio`, flush delay, guard double `unassign`); cap multipart dict + cancel timers; document CLI IN-PLACE version behavior (`runner.py:175-176`).
- Verify: `rg` for `nvidia-smi|cuda|_files|shutdown_event|multipart_archives`.

#### C4. Gemini remote cleanup + logging hygiene (S5/E3/S3)
- Files: `headlinebot/utils.py`, `headlinebot/bot_classes.py`, `main.py`, `colab/bootstrap.py`.
- Steps: `finally: files.delete(audio_file.name)`; standardize on `log()` with `LOG_LEVEL`; rotate `bot.log`; enrich heartbeat (uptime, disk, queue); escape Markdown for filenames/errors, truncate exceptions, strip paths.
- Verify: `rg -n "files\.delete|escape_markdown|bot\.log|HEARTBEAT"`.

### Group D — P2 hygiene (pins, CI, ignore, docs, defaults)

#### D1. Pins + CPU deps + CI
- Files: `requirements.txt`, `requirements_cpu.txt`, `.github/workflows/ci.yml`, `pyproject.toml`.
- Steps: add `>=lower,<next-major` bounds (especially `python-telegram-bot`, `gradio`, `google-genai`, `faster-whisper`); justify/remove `more-itertools`/`tqdm` or keep as transitive with comment; fix CI to `requirements_cpu.txt` + `ruff check` + `compileall`; remove `F401` ignore or scope per-line.
- Verify: CI file read-back; `ruff check` clean (except agreed exceptions); `compileall` 0.

#### D2. Ignore + caches + docs + defaults
- Files: `.gitignore`, `README.md`, `agent.md`, `headlinebot/config.py`, `.env.example`.
- Steps: ignore `.ruff_cache/`, `uploads/`, `transcripts/`, `edited_images/`, `hb-run/`, `*.log`, `colab/hb.tar.gz`, `colab/bootstrap.conf`; remove `__pycache__`/`.ruff_cache`/`.vscode` if tracked; fix `setup_uv.sh`/`walkthrough.md` refs or add files; document `WHISPER_* GPU-only`, `VAD_* advanced`, `ENABLE_GEMINI_FEATURES` default + cost; consider `BEAM_SIZE 10→5`, `JPEG_QUALITY 95→92`, `WHISPER_PRECISION` rename with `USE_FP16` alias; add startup janitor for old `uploads/*.part`/`extract_*`.
- Verify: `git status --porcelain` clean of caches; `git check-ignore` for new patterns; docs `rg` no dead refs.

## Verification (per group, plus final)

```bash
git branch --show-current
git status --porcelain
git diff --stat
python3 -m compileall -q .
python3 -m ruff check . --output-format=concise
rg -n "CallbackQueryHandler|filters\.Chat|chat_filter" --glob '*.py' .
rg -n "os\.system|shell=True|os\._exit|extractall|ZipFile|secure_filename" --glob '*.py' --glob '*.sh' .
rg -n "models_ready_event\.|SHUTDOWN_IN_PROGRESS|shutdown_imminent|perform_shutdown" --glob '*.py' .
git check-ignore -v .env report.md fix-plan.md
```

Group done criteria: commands above pass, changed files read back, no secrets in diff (`rg` for `ghp_|AIza|hf_|bot[0-9]+:` returns nothing), no commit/push yet.

## Risks / open questions

- `report.md` is currently untracked; staging it makes diff large (49.8K) — intended per preference, but review will be noisy. Alternative is separate commit for `report.md` vs `fix-plan.md` (decide at commit time, not now).
- P0+P1+P2 is wide; Groups C–D may conflict (e.g. config centralization touches same lines as idle/shutdown fixes). Land A→B→C→D in order, rebase if needed.
- VRAM/latency (`BEAM_SIZE`, `float16`/`int8`), `reply_to 0`, PTB stop order, Gemini retention need runtime confirmation (see `report.md` Phase 2 UNVERIFIED). Do not change defaults without throwaway GPU run.
- `TELEGRAM_CHAT_ID` single-user vs group determines S1 severity; confirm before choosing allowlist model.
- No commit/push approved in this plan; next approval needed for commit message, staging review, and remote push/PR.

---

## Appendix V — Validated Details (web research 2026-09-07, Full P0+P1+P2)

Sources are live docs fetched this session. Code refs are repo `file:line`. Where docs conflict with installed pins, installed behavior wins; mark UNVERIFIED if version-dependent.

### V1. PTB shutdown order — corrects Group A3/C3
- Validated: `run_polling()` order is `initialize → post_init → Updater.start_polling → start → run until stop → Updater.stop → stop → post_stop → shutdown → post_shutdown`.
  - https://docs.python-telegram-bot.org/en/v22.2/telegram.ext.application.html
  - https://github.com/python-telegram-bot/python-telegram-bot/blob/v22.8/src/telegram/ext/_application.py
- Validated: `Application.stop()` does NOT stop `Updater`; it stops processing, `job_queue`, persistence. Quote: `This does not stop updater. You need to either manually call Updater.stop() or use run_polling/run_webhook`.
- Validated: from inside handler/job/error callback, use `stop_running()`, not `stop()`. `stop_running()` is designed for `run_polling`/`run_webhook` and still runs `Updater.stop → stop → post_stop → shutdown → post_shutdown`.
- Correction to plan: `perform_shutdown()` calling only `application.stop()` (`main.py:185-189`) is incomplete. Fix must be either `await application.updater.stop(); await application.stop(); await application.shutdown()` in that order, or preferably `application.stop_running()` when called from callback context, plus explicit task cancellation (`queue_processor`, `idle_monitor._task`) and `shutdown_gradio()` before runtime unassign. Add 1s flush delay after Telegram notify before stopping.
- UNVERIFIED: exact PTB version installed here is unpinned (`requirements.txt` has `python-telegram-bot` unbounded). Confirm with `pip show python-telegram-bot` in target env; v22.2 changed `retry_after` to `timedelta` (see V4), v22 removed timeout args from `run_polling` (use `ApplicationBuilder` instead — current `HTTPXRequest` tuning at `main.py:798-804` is still valid, but do not pass timeouts to `run_polling`).

### V2. Callback authz — corrects Group B1 (important correction)
- Validated: `CallbackQueryHandler(callback, pattern=None, game_pattern=None, block=True)` takes NO `filters` argument.
  - https://docs.python-telegram-bot.org/en/v22.6/telegram.ext.callbackqueryhandler.html
  - https://docs.python-telegram-bot.org/en/v21.8/telegram.ext.callbackqueryhandler.html
- Correction: plan text `add filters=chat_filter` is WRONG and would raise `TypeError`. Correct fix is manual guard at top of `button_callback()` (`main.py:748-786`):
  ```python
  chat_id = update.effective_chat.id if update.effective_chat else None
  if chat_id != TELEGRAM_CHAT_ID:
      await query.answer("Denied.", show_alert=True)
      return
  ```
  plus `pattern=` to split handlers (e.g. `CallbackQueryHandler(cb, pattern=r"^shutdown_bot$")`) and confirm step for shutdown. Log `query.from_user.id`. `filters.Chat(chat_id=...)` remains correct only for `CommandHandler`/`MessageHandler` (`main.py:869-873`).
- `filters.chat` docs confirm allowlist semantics (`chat_id`, `username`, `allow_empty=False`).

### V3. Markdown escaping — validates Group C4
- Validated: `telegram.helpers.escape_markdown(text, version=1)` escapes `_*` + backtick + `[` for classic Markdown; `version=2` escapes `\_*[]()~` + backtick + `>#+-=|{}.!`, with `entity_type` variants for `pre`/`code`/`text_link`.
  - https://docs.python-telegram-bot.org/en/v22.4/telegram.helpers.html
  - https://github.com/python-telegram-bot/python-telegram-bot/blob/v22.6/src/telegram/helpers.py
- Fix stays: wrap all user-controlled interpolations (`job.original_filename`, `job_name`, `base_name`/`zip_name`, `str(error)`) with `escape_markdown(..., version=1)` since repo uses `ParseMode.MARKDOWN` (`main.py:164,589,679,920`). Do not switch to MARKDOWN_V2 without re-escaping everything.

### V4. Flood vs fatal — validates Group B4
- Validated: `Forbidden` = bot lacks rights (ex-`Unauthorized`, v20 rename). `RetryAfter.retry_after` = seconds to wait (int, v22.2 also accepts `timedelta`; `PTB_TIMEDELTA` opts into timedelta early).
  - https://docs.python-telegram-bot.org/en/latest/telegram.error.html
  - https://github.com/python-telegram-bot/python-telegram-bot/blob/v22.7/src/telegram/error.py
- Validated: PTB `network_retry_loop` treats `RetryAfter` as `slack 0.5s + retry_after`, `TimedOut` as retry ASAP, `InvalidToken` as abort, other `TelegramError` via `on_err_cb`.
  - https://github.com/python-telegram-bot/python-telegram-bot/blob/dc587ade/src/telegram/ext/_utils/networkloop.py
- Wiki warns constant retry on `RetryAfter` wastes resources and risks ban; use `AIORateLimiter`/`BaseRateLimiter`.
  - https://github-wiki-see.page/m/python-telegram-bot/python-telegram-bot/wiki/Avoiding-flood-limits
- Fix stays with one addition: implement `AIORateLimiter` if flood recurs, not just sleep. Remove `Forbidden` from transient tuple (`main.py:887-899`), honor `context.error.retry_after` (handle both int and timedelta), use timestamped window for counts.

### V5. Tar/zip slip — validates + hardens Group B3
- Validated: Python 3.12 added `filter=`; 3.14 defaults to `data` (was `fully_trusted`). Use `hasattr(tarfile, 'data_filter')` feature check, not version check. `data` blocks absolute paths/outside-destination links, clears suid/sgid, normalizes link targets, but does NOT prevent all issues (DoS, pre-existing symlink races). Extract to fresh temp dir, clean up on failure.
  - https://docs.python.org/3/library/tarfile.html
  - https://peps.python.org/pep-0706/
- Validated risk even with filter: CVE-2025-4517 (`data`/`tar` bypass → outside write, fixed in patched 3.12+), CVE-2026-7774 (`data_filter` symlink bypass). NVD: https://nvd.nist.gov/vuln/detail/CVE-2025-4517
- Correction: `filter='data'` is necessary but NOT sufficient for untrusted Telegram ZIPs/TARs. Keep manual `ZipInfo` validation (reject absolute, `..` parts, symlinks, size cap) even after adding tar filter. `zipfile` has no `filter=` API (PEP 706 deferred); manual check is the only path. Current repo Python target is 3.10 (`pyproject.toml`), so `filter=` may not exist — code must branch on `hasattr`.
- Files: `headlinebot/bot_classes.py:439-446`, `runner.py:117-118`, `colab/bootstrap.py:63-64`.

### V6. faster-whisper manifest — corrects Group C3
- Validated: `download_model()` allowlist is `config.json, preprocessor_config.json, model.bin, tokenizer.json, vocabulary.*`.
  - https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/utils.py
- Correction: repo hardcodes only 4 files (`main.py:296`: `config.json, model.bin, tokenizer.json, vocabulary.txt`), missing `preprocessor_config.json` and using `vocabulary.txt` instead of `vocabulary.*` glob. Larger/mismatched `MODEL_SIZE` values will fail or load stale cache. Prefer `faster_whisper.utils.download_model(size, output_dir, ...)` with `allow_patterns` above instead of raw HTTP, or at minimum add `preprocessor_config.json` + `vocabulary.*` handling + size verification + `local_files_only` fallback.
- Validated: `compute_type` options are `float32, float16, int8_float16, int8, default`; `device` is `cpu/cuda/auto`. Conversion-time quantization (`float16/int8/...`) interacts with runtime `compute_type`.
  - https://deepwiki.com/SYSTRAN/faster-whisper/7-model-management and `/9-api-reference`
- `torch.cuda.is_available()` vs `nvidia-smi` check was rate-limited this session (429) — stays UNVERIFIED from web. Keep plan fix (require both signals for WHISPER) and confirm on target image with `python -c "import torch; print(torch.cuda.is_available())"` + `nvidia-smi`.

### V7. Gemini Files delete/retention — validates Group C4
- Validated: `client.files.delete(name=myfile.name)` (`files/{id}` or short id), auto-delete after 48h, manual delete recommended, `try/finally` or context-manager pattern, sync + `aio` variants.
  - https://ai.google.dev/gemini-api/docs/files
  - https://ai.google.dev/api/files
  - https://googleapis-python-genai-70.mintlify.app/api/files/delete
- Example pattern to adopt in `transcribe_with_gemini()` (`headlinebot/utils.py:223-280`):
  ```python
  audio_file = client.files.upload(file=local_filepath)
  try:
      # poll ACTIVE, generate_content via try_model_chain
      ...
  finally:
      try: client.files.delete(name=audio_file.name)
      except Exception: log("GEMINI", "remote delete failed")
  ```
- Retention note for journalists: 48h auto-delete does not replace explicit delete; document source-protection policy.

### V8. Git token without ps/log exposure — validates Group B2
- Validated problem: token in clone URL appears in `argv`/`ps`/`/proc/*/cmdline`, audit logs, monitoring bundles, and persists in `.git/config` via `remote get-url`.
  - https://github.com/Finsys/dockhand/issues/1081
  - http://public-inbox.org/git/xmqqsewtvsrg.fsf@gitster.g/T/
- Validated fixes (prefer in this order): `GIT_ASKPASS` helper, `credential.helper`, transient `http.extraHeader` via `GIT_CONFIG_COUNT/KEY_0/VALUE_0` env (not `git -c` argv), token-free `SAFE_ORIGIN_URL` + post-clone hardening (`remote set-url` scrub + regression test asserting `get-url` has no token).
  - https://developers.cloudflare.com/artifacts/api/git-protocol/
  - https://github.com/github/gh-aw/pull/54701
- Apply to `runner.py:188-193,193`: never `f"https://{token}@"`, never log full command. Use env-carried header + `subprocess.run([...], shell=False)` + `redact()` logger. Rotate any PAT previously used with old code if host logs are shared.

### V9. Werkzeug filename scope — validates Group D1 pin note
- Validated: `secure_filename()` returns ASCII-portable name for `os.path.join`, may return empty (caller must handle uniqueness — repo already prefixes `uuid4().hex`, good). It only sanitizes name, not filesystem properties; symlinks allowed, system expected trusted.
  - https://tedboy.github.io/flask/generated/werkzeug.secure_filename.html
  - https://github.com/pallets/werkzeug/pull/3252
- Validated: `safe_join` Windows device-name bypass fixed in 3.1.6 (CVE-2026-27199, GHSA-29vq-49wr-vm6x). Pin `werkzeug>=3.1.6` (repo runs Linux, low severity, but pin anyway).
- No change to `secure_filename` usage (`bot_classes.py:351,361,365,371,404,453`, `main.py:579`); keep `uuid + secure_filename` pattern, add empty-result guard.

### What changed in fix-plan.md due to validation
- B1: replaced `add filters=` with manual `effective_chat` guard + `pattern=` split (V2).
- A3/C3: replaced bare `application.stop()` with `updater.stop → stop → shutdown` / `stop_running()` ordering (V1).
- B3: added `hasattr(tarfile,'data_filter')` branch + keep manual ZIP checks despite filter (V5 + CVEs).
- C3: added missing `preprocessor_config.json` + `vocabulary.*` to manifest fix (V6).
- C4: adopted `try/finally files.delete` pattern (V7).
- B2: adopted `GIT_CONFIG_COUNT` header auth, not `git -c` (V8).
- D1: added `werkzeug>=3.1.6` floor (V9).
- UNVERIFIED kept: T4 VRAM/latency numbers, `reply_to 0` exact `BadRequest` text, installed PTB major version, `torch.cuda` vs `nvidia-smi` on target image.

