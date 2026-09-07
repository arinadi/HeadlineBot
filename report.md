# HeadlineBot Audit Report — Deadcode, Unused, Fixes & Feature Suggestions

Date: 2026-09-07 (UTC)
Scope: `main.py`, `runner.py`, `start.py`, `headlinebot/*.py`, `colab/*`, `presets.json`, `requirements*.txt`, `.env.example`, `pyproject.toml`, `.github/workflows/ci.yml`, `README.md`, `agent.md`
Method: read-only code read + `ruff check` + `rg` cross-reference (defs vs usages). No runtime execution with secrets.
Policy: English only. No code changes in this report.

## Executive Summary

HeadlineBot works, but has significant deadcode and broken wiring that makes 3 advertised features effectively disabled:

1. **Image presets never load** — `headlinebot/image_editor.py:32` points to `headlinebot/docs/presets.json`, which does not exist. Real file is repo-root `presets.json`. Result: `_load_presets()` always falls back to empty, `_get_preset()` returns `{}`, all `condition` handling degrades to `DAYLIGHT` or defaults.
2. **Gradio Web UI never starts** — `main.py:230,272` does `import gradio_handler` (top-level) instead of `from headlinebot import gradio_handler` or `import headlinebot.gradio_handler`. This always raises `ImportError`, so `GRADIO_AVAILABLE` stays `False`. `initialize_gradio_background()` early-returns at `main.py:412`. Also `shutdown_gradio()` and `gradio_ready_event` in `headlinebot/gradio_handler.py:24,271` have zero callers/awaiters.
3. **Summary/retouch/photo AI is gated off by default and bypassed** — `Config.ENABLE_GEMINI_FEATURES` defaults to `false` (`headlinebot/config.py:78`, `.env.example:36`, `README.md:347`). `main.py:539-540,599-600` re-reads `os.getenv('ENABLE_GEMINI_FEATURES')` instead of `Config`, so even if config is fixed the path is duplicated. With default `false`, `summarize_text`, `retouch_transcript`, `edit_image` are imported but never produce output; user still pays model-discovery cost.

Fix-first recommendation: do **P0 wiring fixes only** before any new features. New features are listed as P2/opt-in because queue, shutdown, and CPU-boot paths are currently fragile.

---

## 1. Deadcode & Unused Inventory (with evidence)

### 1.1 Duplicated helpers

| Item | Location | Evidence of duplication / deadness |
|---|---|---|
| `detect_platform()` duplicated | `runner.py:8` vs `headlinebot/utils.py:10` | Same logic (kaggle > colab > local). `headlinebot/secrets.py:20` imports from `utils`, `runner.py:152` uses local copy. Keep one in `utils`, import in `runner`. |
| `GEMMA_MODEL`, `JPEG_QUALITY` defined 3x | `headlinebot/config.py:82-85`, `headlinebot/image_editor.py:26-27`, `headlinebot/utils.py:46` | Three sources of truth. `image_editor` uses its own env read, `utils.get_model_chain()` uses hardcoded `"models/gemma-4-26b-a4b-it"`, `Config` is never read for image path. Divergence risk. |
| `TELEGRAM_CHAT_ID` read 2x | `headlinebot/config.py:11` (int-converted) vs `headlinebot/gradio_handler.py:38-43` `_get_telegram_chat_id()` (re-reads `os.environ`) | Gradio path ignores `Config`, duplicates parsing. |
| `IDLE_*` aliases vs `Config` | `main.py:68-70` aliases, mutated at `main.py:824-827` (`*=5`), but `headlinebot/bot_classes.py:90,149,182-195` reads `Config.*` directly | Multiplier has zero effect. `IdleMonitor` was already constructed with `Config` values at `main.py:860`. Dead logic + misleading log at `main.py:832`. |
| `TRANSCRIPTION_MODE` read 3x | `main.py:28`, `headlinebot/bot_classes.py:289`, `start.py:29` sets it | `bot_classes` re-reads env per file instead of receiving mode via constructor. |

### 1.2 Unused / never-called functions, vars, params

| Item | Location | Why dead |
|---|---|---|
| `genai = None` global | `main.py:46` | Only used as local `from google import genai` at `main.py:363,394`. Global never read. Remove. |
| Duplicate `model = None`, `gemini_client = None` | `main.py:44-45` then again `main.py:140-141` | Second pair shadows first. Keep one block. |
| `import gradio_handler` (2 sites) | `main.py:230,272` | Wrong import path, always fails. Should be `from headlinebot import gradio_handler as _gh` or `import headlinebot.gradio_handler`. |
| `gradio_handler = None` module global shadow | `main.py:43,210,411` | After failed import, `gradio_handler` stays `None`, so `main.py:412` `if not GRADIO_AVAILABLE or not gradio_handler: return` is always true. Gradio dead. |
| `shutdown_gradio()` | `headlinebot/gradio_handler.py:271-279` | Zero callers (`rg shutdown_gradio` only def). No graceful shutdown hook in `perform_shutdown()`. |
| `gradio_ready_event` | `headlinebot/gradio_handler.py:24,261` | Set but never awaited. Dead sync primitive. |
| `build_journalist_summary_prompt(..., file_metadata=None)` | `headlinebot/utils.py:71` | `summarize_text()` at `utils.py:143` never passes `file_metadata`. Param is dead; either wire metadata or remove param. |
| `_process_image_job(job, _start_time)` | `main.py:526` | `_start_time` prefixed unused, never read inside. Remove param or use for duration log. |
| `elapsed = get_runtime()` in worker heartbeat | `main.py:645` | Computed but log at `main.py:649` only uses `qsize`/`status`. `elapsed` unused. |
| `transcript_text` cleanup in `finally` | `main.py:689-691` | Checks `'transcript_text' in locals()` inside `queue_processor()`, but `transcript_text` lives in `_process_transcript_job()` scope. Condition always False, `gc.collect()` never runs for this. Dead. |
| `format_transcription_native` doc vs impl | `headlinebot/utils.py:205-221` | Docstring says `Format: [HH:MM:SS] Text`, impl strips to `text` only (`lines.append(f"{text}")`). Either doc or timestamp logic is dead/misleading. `get_val()` at `utils.py:197` only used here. |
| `MODEL_CATEGORIES` gemma/flash split, `transcript_chain` vs `gemma_chain` | `headlinebot/model_manager.py:42-46,174-182` | With `ENABLE_GEMINI_FEATURES=false`, summary/retouch/photo chains are built via `discover_models()` but never consumed. Discovery cost with no benefit in default config. |
| `run_command()` vs `run_command_streaming()` | `runner.py:37-54,212-215` | `run_command_streaming` only used for kaggle branch. Non-kaggle uses `os.system` wrapper with no output capture. Consolidate. |
| `HEADLINEBOT_BRANCH` | `runner.py:137` set, never read | No consumer. Either use for logging or remove. |
| `IDLE_FIRST_ALERT_MINUTES`, `IDLE_FINAL_WARNING_MINUTES` env | `headlinebot/config.py:69-72`, `.env.example` only documents `IDLE_SHUTDOWN_MINUTES` | Partially documented, rarely tuned. Keep but document or drop fine-grained knobs. |
| `VAD_*` tuning vars when `VAD_FILTER=False` | `headlinebot/config.py:46-58`, `main.py:501-504` | Default `VAD_FILTER=False`, so `VAD_THRESHOLD`, `VAD_MIN_*`, `VAD_SPEECH_PAD_MS` are parsed but unused in default path. Not dead if user enables, but noisy. Document as advanced-only. |
| `WHISPER_*` vars in GEMINI mode | `main.py:54-65`, `headlinebot/config.py:21-42` | In CPU/GEMINI mode (default without GPU), all Whisper beam/patience/temperature/precision vars are loaded but never used. Expected, but should be grouped as `WHISPER_* (GPU only)`. |
| `COMBINE_TIMEOUT_SECONDS`, multipart ZIP flow | `headlinebot/bot_classes.py:267,369-432` | Not dead, but low usage vs complexity. Keep only if field journalists actually send `.zip.001` splits. Candidate for feature-flag. |
| `context: ContextTypes.DEFAULT_TYPE` in `FilesHandler.handle_files` | `headlinebot/bot_classes.py:321` | Unused arg (`ARG002` in ruff-all). Required by PTB signature — keep but mark `_context` or add noqa. Same for `update`/`context` in commands where unused. |

### 1.3 Unused dependencies, files, docs references

| Item | Evidence |
|---|---|
| `requirements_cpu.txt` incomplete | Contains only `ffmpeg-python, python-telegram-bot, nest_asyncio, werkzeug`. But `runner.py:205` installs it then `start.py -> main.py` unconditionally imports `headlinebot.image_editor` (`cv2`, `numpy`, `PIL` at `image_editor.py:17-19`) and `headlinebot.secrets` needs `requests` (`secrets.py:19`). On a minimal CPU image without preinstalled deps, boot fails with `ImportError`. `requirements.txt` has them, `requirements_cpu.txt` does not. |
| `requirements.txt` has `more-itertools, tqdm, httpx>=0.28.1` with no direct import | `rg "^import|^from"` shows no `more_itertools`, `tqdm`, `httpx` usage in own code (httpx used indirectly via `telegram.request.HTTPXRequest`). Either remove or pin as transitive. `gradio>=4.0.0` is imported only in `gradio_handler` (dead path currently). |
| CI references missing file + wrong linter | `.github/workflows/ci.yml:22` checks `requirements_local.txt` (does not exist), installs `flake8` but repo standard is `ruff` (`pyproject.toml`, `README.md:391`, `agent.md`). `flake8` run will pass while `ruff` failures (e.g. broken imports) are missed. |
| `pyproject.toml` ignores `F401` | `pyproject.toml:17` ignores unused imports. This hides real dead imports (e.g. `main.py:77` `UserSecretsClient` imported but unused except for detection — should use `importlib.util.find_spec`). Remove `F401` from ignore or add per-line noqa with reason. |
| `agent.md:27` references `setup_uv.sh`, `agent.md:73` references `walkthrough.md`, `agent.md:41` references `AI_...` output | None exist in repo (`glob` shows no `setup_uv.sh`, no `walkthrough.md`). Stale docs. `README.md:290-310` file structure lists `headlinebot/docs/presets.json` implicitly? Actually lists package files but omits `presets.json` location mismatch. |
| `.gitignore` minimal | Only `__pycache__`, `.env`. Missing `.ruff_cache/`, `uploads/`, `transcripts/`, `edited_images/`, `hb-run/`, `*.log`, `.env`, `colab/hb.tar.gz`, `colab/bootstrap.conf`. Result: `__pycache__/`, `.ruff_cache/`, `.vscode/` present on disk risk being committed. |
| `colab/__pycache__/`, `headlinebot/__pycache__/`, `.ruff_cache/`, `.vscode/` on disk | Should not be in repo. Add to ignore + clean. |
| `presets.json` at root vs expected `headlinebot/docs/presets.json` | `image_editor.py:32` vs `ls headlinebot/docs` → `No such file`. Confirmed broken. Also `agent.md` never mentions presets location. |

---

## 2. Bugs & Fragile Wiring (fix before features)

### P0 — Breaks advertised functionality

1. **Presets path wrong (`headlinebot/image_editor.py:32`)**
   - `os.path.join(os.path.dirname(__file__), "docs", "presets.json")` → `headlinebot/docs/presets.json` (missing).
   - Real file: repo-root `presets.json`.
   - Fix: move to `headlinebot/presets.json` or `headlinebot/data/presets.json` and update `_PRESETS_PATH`, or resolve repo-root relative. Add startup assert + test that `len(_PRESETS_DATA.get('presets',{}))==16`.
   - Secondary: `PORTRAIT` lock `"l": [-8, -15]` in `presets.json:170` is reversed (min > max). `_apply_locks()` at `image_editor.py:71` does `np.clip(x, -8, -15)` → always `-15`. Fix to `[-15, -8]`. Also `parameter_locks` in JSON vs hardcoded locks in `CORRECT_PROMPT_TEMPLATE` (`image_editor.py:127-131`) diverge (`BACKLIGHT h_max -30` vs `-25`, `GREEN_SPILL s_max 1.0` vs `0.95`, missing `c` range). Single-source locks from JSON.

2. **Gradio import + lifecycle broken (`main.py:230,272,376,411-420,454-456,818-819`)**
   - Fix import, remove `gradio_handler=None` shadowing, use `from headlinebot import gradio_handler`.
   - `initialize_models_background()` at `main.py:376-377` and `post_init()` at `main.py:818-819` both schedule `initialize_gradio_background()` → double launch. Keep one.
   - `update_startup_message()` at `main.py:454` accesses `gradio_handler.gradio_app` but module var is `gradio_app` — works only if import fixed; add `get_share_url()` helper instead of reaching into module global.
   - Wire `shutdown_gradio()` into `perform_shutdown()`.
   - If Gradio is intentionally WHISPER-only, document + guard: skip launch in GEMINI mode instead of silent no-op.

3. **CPU boot imports heavy deps unconditionally (`main.py:23`, `headlinebot/image_editor.py:17-19`)**
   - `from headlinebot.image_editor import edit_image` at top level pulls `cv2`/`numpy`/`PIL` even in GEMINI/CPU mode where `requirements_cpu.txt` lacks them.
   - Fix: lazy-import `edit_image` inside `_process_image_job()` (like `transcribe_with_gemini` at `main.py:570`), and add `requests`, `google-genai` (or `google-genai` package name check), `opencv-python-headless`, `Pillow`, `numpy` to `requirements_cpu.txt` OR keep CPU image truly light and make image path optional with clear log.

4. **Idle timer multiplier is no-op (`main.py:824-827` vs `bot_classes.py:182-195`)**
   - Mutates globals, `IdleMonitor` reads `Config`.
   - Fix: add `IdleMonitor.set_multipliers()` or compute effective timeouts at construction in `main()` before `IdleMonitor(application, ...)` at `main.py:860`. Remove globals or make them single source.

### P1 — Reliability / correctness

5. **Stale `Config` aliases (`main.py:49-70`)**
   - `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `WHISPER_*`, `BOT_FILESIZE_LIMIT` are snapshotted at import. If `runner.py` or `bootstrap.py` mutates `os.environ` after import, aliases are stale. Fix: read `Config.*` at use site, or add `Config.reload()` after secrets load. At minimum, keep secrets (`TELEGRAM_*`, `GEMINI_*`) as properties, not module constants.

6. **`Job` dataclass fragile (`headlinebot/bot_classes.py:27-67`)**
   - `author_display_name: str = field(init=False)` with no default + `_original_message` private but accessed externally at `main.py:546,551,556` (`job._original_message.reply_photo` vs `application.bot.reply_photo` inconsistency).
   - Fix: give `author_display_name: str = "Unknown"`, make `_original_message: telegram.Message | None = None`, add `Job.reply_photo()`/`reply_text()` helpers, avoid private access from `main.py`. Also `job_type` comment says `"transcript"` but `FilesHandler` uses `"transcript"` default and `"image"`; `main.py:667` checks `"image"` else transcript — document union or use `Literal["transcript","image"]`.

7. **`_validate_and_queue_file()` fake message hack (`bot_classes.py:302-311`)**
   - Builds `type('obj',...)` fakes to reuse `Job.from_message`. Fragile, breaks type checkers.
   - Fix: add `Job.from_parts(message_id, chat_id, from_user, chat_title, filename, ...)` and call directly.

8. **Whisper download hardcoded file list (`main.py:296-348`)**
   - `_files = ["config.json","model.bin","tokenizer.json","vocabulary.txt"]` assumes `large-v2` layout. Other `MODEL_SIZE` values may need different files. No checksum/size check, no `HF_TOKEN` refresh, `os.rename` not atomic across filesystems. Add manifest fetch or delegate to `faster-whisper` downloader with `local_files_only` fallback. At minimum, log expected bytes and verify `model.bin` size.

9. **`nest_asyncio` + `asyncio.run` patch (`main.py:109-123`)**
   - Monkey-patches `asyncio.run` to swallow `loop_factory`. Needed only for Gradio+Colab interaction. If Gradio stays disabled, this is dead complexity. Isolate to `gradio_handler.launch_gradio_async()` with comment + version pin, or remove if `gradio>=5` fixes it.

10. **Error handler swallows transient errors without backoff accounting (`main.py:877-926`)**
    - `_transient_error_counts` dict grows per error name, resets only on non-transient. `RetryAfter` should respect `retry_after` seconds. `Forbidden` is not transient (bot blocked/removed) — should shutdown/notify, not retry. Split `transient_network` vs `rate_limit` vs `fatal`.

11. **Secrets fallback silent (`headlinebot/secrets.py:123-146`)**
    - `load_all_secrets()` returns `{}` on both kaggle/colab without Infisical and on local without env. Caller `runner.py:169` only checks `TELEGRAM_*`, so misconfigured Infisical falls through to cryptic `Missing secrets` without showing which env (`dev/staging/prod`) was queried. Log `project_id` suffix + `environment` (never values).

12. **Runner git + token handling (`runner.py:177-199`)**
    - `run_command(f"git fetch ...")` via `os.system` with interpolated `branch`; `clone_url.replace("https://", f"https://{token}@")` leaks token in `ps` + logs (`Executing: ...` prints full URL with token). Fix: use `subprocess.run([...], ...)` list form, set `GIT_ASKPASS` or `http.extraHeader` with `Authorization`, never log token. Also `download_repo_fallback()` uses `urllib` without checksum.

### P2 — Hygiene

13. **Ruff/CI mismatch, `F401` ignored, no tests.**
14. **`.gitignore`, cache dirs, `__pycache__` committed risk.**
15. **Stale docs (`agent.md`, `README.md` Colab cell duplicates Infisical logic already in `secrets.py`).**
16. **Logging via `print` + `log()` mix (`bot_classes.py:274,373,422,428`, `bootstrap.py:68,88,92,105`).** Standardize on `log()` with categories.
17. **Blocking `os.path`/`open` in async (`bot_classes.py:298,318,417,431,464`) flagged by `ASYNC240/ASYNC230`.** Wrap in `to_thread` or accept with noqa + reason (low traffic, fine).

---

## 3. Recommended Fixes (ordered, smallest diff first)

### P0 (do now, no new features)

- [ ] **F1. Fix presets path + locks.** Move `presets.json` → `headlinebot/presets.json` (or fix `_PRESETS_PATH` to repo-root), fix `PORTRAIT l` to `[-15,-8]`, generate prompt locks from JSON (remove hardcoded `CORRECT_PROMPT_TEMPLATE` locks). Test: import `image_editor`, assert 16 presets, `_get_preset("BACKLIGHT")` non-empty, `_apply_locks` clamps correctly.
- [ ] **F2. Fix Gradio import + single launch + shutdown.** Correct import, remove double `create_task(initialize_gradio_background())`, add `shutdown_gradio()` call in `perform_shutdown()`. Verify: `GRADIO_AVAILABLE` true when `gradio` installed, startup message shows URL, no double bind.
- [ ] **F3. Make CPU boot import-safe.** Lazy-import `edit_image`/`cv2` path, fix `requirements_cpu.txt` (add `requests`, `google-genai`, `Pillow`, `numpy`, `opencv-python-headless` OR document CPU-no-photo mode). Verify: fresh `pip install -r requirements_cpu.txt` + `python -c "import main"` succeeds without GPU deps? Currently fails — must pass after fix.
- [ ] **F4. Fix idle timers.** Replace globals mutation with `IdleMonitor` effective-timeout method. Verify: logs show `5x` timeouts actually used in GEMINI mode.
- [ ] **F5. Harden runner token handling.** No token in logs/`ps`, list-form subprocess. Verify: `ps aux` + log grep shows no token.

### P1 (next)

- [ ] **F6. Remove `F401` ignore, fix unused imports, unify `detect_platform`, `GEMMA_MODEL`, `TELEGRAM_CHAT_ID` single source.**
- [ ] **F7. Fix `Job` dataclass + remove fake-message hack + unify `reply_photo` path.**
- [ ] **F8. Fix CI:** replace `flake8` with `ruff check .`, fix `requirements_local.txt` → `requirements_cpu.txt`/`requirements.txt`, add `ruff format --check` or `python -m compileall`.
- [ ] **F9. Expand `.gitignore`, delete caches (`__pycache__/`, `.ruff_cache/`, `.vscode/` if local-only).**
- [ ] **F10. Standardize config access (no stale aliases), document `WHISPER_* (GPU only)` vs `GEMINI/*` vs `VAD_* (advanced)`.**
- [ ] **F11. Correct `format_transcription_native` docstring (no timestamps) or re-add timestamps if journalists need them.**

Verification for all: `python -m ruff check . --output-format=concise` clean (without `F401` ignore), `python -m compileall -q .`, manual `rg` that each removed symbol has zero refs.

---

## 4. Feature Suggestions — Only If P0 Done (fix-first, opt-in)

Do not build these until F1–F5 land. Each is small, isolated, and reversible.

### Keep (low cost, high journalist value)

1. **`/help` + `/retry` + `/cancel` parity.** Currently `status/queue/extend` exist (`main.py:869-871`) but no `/help`. Add `/help` text reusing `get_status_text_and_keyboard()`. `/retry <job_id>` only for `failed` jobs (keep last error). Cost: ~30 lines, no new deps.
2. **Healthcheck + `/ping` with model readiness.** Expose `models_ready_event.is_set()`, `MODE`, queue depth. Helps Colab/Kaggle debugging where logs are hard to tail. Reuses `get_status_text_and_keyboard()`.
3. **Transcript language + duration in filename/metadata.** Already have `detected_language`, `duration_str` (`main.py:565-580`). Also write `.json` sidecar (`filename, duration, lang, model, timestamp`) for redaksi archiving. No new deps.
4. **Graceful `/stop` with queue drain option.** Current `shutdown_bot` kills immediately (`main.py:759-761`). Add `Drain & stop` vs `Stop now` buttons. Reuses `JobManager.get_queued_jobs()`.
5. **Config validation at startup (`--check`).** Fail fast if `TELEGRAM_CHAT_ID` not int, `BOT_FILESIZE_LIMIT<=0`, `IDLE_*` ordering (`first < final < shutdown`), `MODEL_SIZE` unknown. Prevents silent misconfig. Pure function + test.

### Defer / Do not build yet

- **Database, multi-user auth, web dashboard auth, payments, multi-language UI.** No evidence of need; adds state to ephemeral Colab/Kaggle VMs. Colab/Kaggle filesystem is ephemeral — persistence must be Telegram + Drive/Cloud, not local DB.
- **New AI models / video editing / live streaming.** Model chain (`model_manager.py`) already handles fallback; adding modalities before fixing presets/Gradio multiplies untested paths.
- **Full test suite with network mocks.** Valuable but heavy. Start with 5 pure-function tests only: `extract_version`, `filter_models`, `build_model_chain`, `_apply_locks`, `format_duration`/`format_transcription_native`. No Telegram/Gemini mocks needed.

### Minimal test seed (suggested, not required for this report)

- `test_model_manager.py`: `extract_version("gemini-3.5-flash")>(2,5)`, `filter_models` excludes `-tts/-image/embedding`, `build_model_chain` primary is newest.
- `test_image_locks.py`: `PORTRAIT l` clamp, `BACKLIGHT d_min/h_max`, `GREEN_SPILL t/s_max`.
- `test_utils_format.py`: `format_duration(-1)=="N/A"`, `format_transcription_native([])==""`, prompt builders contain `FAKTA BERITA` / `LEAD`.

---

## Appendix A — File inventory & ownership

| File | Role | Verdict |
|---|---|---|
| `main.py` (956 lines) | Telegram handlers, worker, init | Split: extract `handlers.py`, `worker.py`, `startup.py`. Too large, mixed concerns. |
| `headlinebot/bot_classes.py` (467 lines) | `Job`, `IdleMonitor`, `JobManager`, `FilesHandler` | Keep, but split `FilesHandler` (ZIP/multipart) to `files.py`. Fix `Job` defaults. |
| `headlinebot/image_editor.py` (522 lines) | Presets + OpenCV | Keep, fix path/locks, add unit tests for pure funcs (`build_contrast_lut`, `is_backlight`, `quality_guard`, `_apply_locks`). |
| `headlinebot/model_manager.py` (262 lines) | Discovery + retry chain | Keep. Good separation. Add tests. |
| `headlinebot/utils.py` (280 lines) | Logging, prompts, Gemini transcribe/summarize | Keep. Remove `file_metadata` dead param or wire it. Fix docstring. |
| `headlinebot/gradio_handler.py` (279 lines) | Web upload | Keep only if Gradio fixed (F2). Else delete to remove dead dep (`gradio>=4.0.0`). |
| `headlinebot/config.py` (85 lines) | Env config | Keep. Make single source, document groups. |
| `headlinebot/secrets.py` (148 lines) | Infisical | Keep. Improve logging, no token leak. |
| `runner.py` (218 lines) | Clone/update, secrets, pip install, launch | Keep. Fix token leak, consolidate `run_command`. Dedupe `detect_platform`. |
| `start.py` (46 lines) | GPU detect → `TRANSCRIPTION_MODE` | Keep. Document `nvidia-smi` vs `torch.cuda` discrepancy (`agent.md` says `torch.cuda`, code uses `nvidia-smi`). |
| `colab/bootstrap.py`, `colab/colab-run.sh` | CLI lifecycle | Keep. Good isolation. Add `set -u` check for `.env` perms (`chmod 600`). |
| `presets.json` | Photo presets | Move under `headlinebot/`, fix locks. |
| `requirements.txt` / `requirements_cpu.txt` | Deps | Fix CPU list (F3), prune unused (`more-itertools`, `tqdm` if truly unused). |
| `.github/workflows/ci.yml` | CI | Fix linter + requirements path (F8). |
| `README.md`, `agent.md` | Docs | Update after F1–F5: correct file structure, remove `setup_uv.sh`/`walkthrough.md` refs or add files, document `ENABLE_GEMINI_FEATURES` default + cost. |

## Appendix B — Commands used for this audit (reproducible)

```bash
python3 -m ruff check . --output-format=concise
python3 -m ruff check . --select F401,F841,F822,F823 --output-format=concise
python3 -m ruff check . --select ALL --ignore E501 --output-format=concise | head -n 200
rg -n "def detect_platform|gradio_handler|GRADIO_AVAILABLE|ENABLE_GEMINI|presets.json|shutdown_gradio|gradio_ready_event" --glob '*.py' .
rg -n "^import|^from" headlinebot/*.py main.py runner.py start.py colab/bootstrap.py | sort | uniq
rg -n "WHISPER_|VAD_|BOT_FILESIZE|IDLE_|ENABLE_|MODEL_SIZE|USE_FP16|BEAM_SIZE|GEMMA_MODEL|JPEG_QUALITY|TRANSCRIPTION_MODE|HEADLINEBOT_" --glob '*.py' --glob '*.txt' --glob '*.example' --glob '*.sh' .
ls headlinebot/docs  # confirms missing (presets path bug)
```

## Appendix C — Risks & open questions

- **No secret-bearing runtime test performed.** Findings are static. Confirm F1–F3 on a throwaway Colab/Kaggle session with dummy tokens before merging.
- **`ENABLE_GEMINI_FEATURES=false` default may be intentional cost control.** If so, document that summary/retouch/photo are intentionally off and remove dead discovery cost (skip `discover_models` for unused tasks). If not intentional, flip default to `true` after quota check.
- **Multipart ZIP + Gradio may have zero real users.** Check Telegram logs for `.zip.001` and Gradio hits. If zero in 30 days, flag for removal to cut ~200 lines.
- **Whisper `large-v2` on T4 lifecycle.** Download + `float16` vs `int8` choice impacts OOM. `WHISPER_PRECISION` via `USE_FP16` naming is confusing (`USE_FP16=auto` holds `float16/int8/float32`). Rename to `WHISPER_PRECISION` with `auto/float16/int8/float32`, keep `USE_FP16` as deprecated alias.

---

# Phase 2 — Deep Audit (concurrency, security, lifecycle, errors, perf, deps)

Date: 2026-09-07 (UTC). Scope: full depth. Method: static + safe runs only (`compileall`, `ruff check`, `rg`, `git status/check-ignore`, `pip index versions` read-only). No secrets accessed, no network mutation, no live GPU/Colab run. Numbers marked UNVERIFIED are estimates needing runtime confirmation.

## 2.1 Concurrency, queue, shutdown races

### C1. Worker starts before Gemini ready in default mode — P0
- `main.py:142-145`: `models_ready_event = asyncio.Event()` + `if MODE == 'GEMINI': models_ready_event.set()` runs at import time, before `initialize_models_background()` creates `gemini_client` and runs `discover_models()` (`main.py:360-369`).
- `queue_processor()` at `main.py:638-639` waits only on that event, so in GEMINI mode it processes immediately while `gemini_client` is still `None`.
- Result: `transcribe_with_gemini()` at `headlinebot/utils.py:227-228` returns `"Error: Gemini client not initialized."`, which is then written to `TS_*.txt` and sent as if it were a transcript (`main.py:571-596`). Silent data corruption, not a crash.
- Fix: do not pre-set event for GEMINI. Set event only after `gemini_client` + `discover_models()` succeed (or fail with fallback chain). Add `gemini_client is not None` guard in worker or return explicit `failed` job instead of writing error-string transcript.

### C2. Single FIFO worker head-of-line blocking — P1 (design, document)
- `JobManager.job_queue = asyncio.Queue()` (`headlinebot/bot_classes.py:215`), one `queue_processor()` task (`main.py:814`), `await job_queue.get()` with 30s timeout (`main.py:653`).
- Gemini poll loop holds worker up to 5 minutes (`headlinebot/utils.py:240-252`: `max_polls=150 * 2s`), Whisper `large-v2` transcribe holds worker for full audio duration (minutes to hours). Images wait behind long audio.
- No priority, no separate image vs transcript queue, no concurrency limit config.
- Fix (doc first): document FIFO + expected wait. Later: separate `image_queue` or `concurrency=2` with VRAM guard. Do not add threads before C1/F3 fixed.

### C3. Cancel of currently-processing job is misleading — P1
- `JobManager.cancel_job()` (`headlinebot/bot_classes.py:248-254`) sets `job.status='cancelled'` for any registry entry, returns `True`.
- Worker checks `job.status=='cancelled'` only before `set_processing_job()` (`main.py:657-663`) and once after Whisper/Gemini transcribe for transcript jobs (`main.py:575-576`). Image path (`main.py:667-668` → `_process_image_job`) has no mid-process cancel check.
- `get_queued_jobs()` (`bot_classes.py:261-262`) filters `status=='queued'`, so UI `view_cancel_jobs` (`main.py:762-769`) only lists queued, but direct `cancel_<id>` callback for a job that just transitioned to `processing` still reports `✅ Job ... was cancelled` (`main.py:772-774`) while work continues.
- Fix: `cancel_job()` should return `(False, ...)` if `currently_processing.job_id==job_id`, or add `job.cancel_requested` flag checked between transcript → summary → retouch stages. Update UI text to `Already processing, cannot cancel`.

### C4. Shutdown is check-then-set without lock + incomplete teardown — P0
- `SHUTDOWN_IN_PROGRESS` bool (`main.py:158,170-173`), `IdleMonitor.shutdown_imminent` bool (`bot_classes.py:86,148`). Three concurrent callers: `button_callback/shutdown_bot` (`main.py:759-761`), `IdleMonitor._handle_shutdown` (`bot_classes.py:147-163`), `global_error_handler` (`main.py:926`).
- Early-return makes double-shutdown mostly harmless, but `queue_processor` loop condition `while not SHUTDOWN_IN_PROGRESS` (`main.py:642`) is evaluated only at top; long `await asyncio.to_thread(run_transcription_process)` / Gemini poll continues after shutdown, then tries `application.bot.send_message` on stopped app (`main.py:679,593-596`), raising, then `finally` deletes local file and marks complete (`main.py:682-694`). No job requeue, no `application.shutdown()`, no `idle_monitor.stop()`, no `shutdown_gradio()` call.
- `perform_shutdown()` (`main.py:168-206`) calls `application.stop()` but not `updater`/`shutdown()`; on Kaggle calls `os._exit(0)` (`main.py:198`) skipping `finally` cleanup and `__main__` safety-net `runtime.unassign()` (`main.py:952-956`) double-runs on Colab path.
- Fix: add `shutdown_event = asyncio.Event()`, make `perform_shutdown` idempotent via `event.is_set()`, cancel `queue_processor` + `idle_monitor._task`, await `application.updater.stop()` + `application.stop()` + `application.shutdown()` in correct PTB order, then `shutdown_gradio()`, then runtime unassign with small flush delay. Document Kaggle `os._exit` as last resort only after flush.

### C5. Gradio cross-thread fire-and-forget lies about success — P0 (if Gradio kept)
- `process_upload()` runs in Gradio server thread (`headlinebot/gradio_handler.py:46-97`), calls `asyncio.run_coroutine_threadsafe(_queue_gradio_job(...), _main_loop)` (`gradio_handler.py:85`) without storing Future or checking `future.result()`.
- `_queue_gradio_job()` (`gradio_handler.py:100-131`) does `ffmpeg.probe` + `Job.from_message` with `message_id=0` + `await _job_manager.add_job(job)` which sends `reply_to_message_id=0` (`bot_classes.py:231`). Telegram `BadRequest` for invalid reply id is caught inside `_queue_gradio_job` as generic `Exception`, file deleted, only server log written. Gradio UI already returned `📤 N file(s) uploaded successfully` (`gradio_handler.py:92-97`).
- `_main_loop` captured once in `set_dependencies()` (`gradio_handler.py:30-35`, called at `main.py:419`); stale after loop restart. No validation that loop is running.
- Fix: return `pending` status from `process_upload`, attach `future.add_done_callback` to edit status or log with job id, use `message_id=None` and skip `reply_to` when `0`, validate `_main_loop.is_running()` before submit.

### C6. Multipart timer leaks + unbounded dict — P1
- `loop.call_later(COMBINE_TIMEOUT_SECONDS, lambda: asyncio.create_task(...))` (`bot_classes.py:382,394`) creates tasks with no handle, no exception callback. If `_process_multipart_archive` raises outside its internal try, unretrieved exception warning only.
- `multipart_archives` dict keyed by attacker-controlled `base_name` (`bot_classes.py:370,390-395`) grows without cap; `COMBINE_TIMEOUT_SECONDS=30` (`bot_classes.py:267`). Shutdown does not cancel timers or delete part files (`bot_classes.py:397-432` finally only deletes on combine path).
- Fix: cap dict (e.g. 20 entries, LRU evict oldest with cleanup), store `TimerHandle`, cancel all on shutdown, delete orphan `*_*.zip.001` on startup.

### C7. Blocking work inside event loop — P2 (low traffic, note)
- Correctly offloaded: `ffmpeg.probe` (`bot_classes.py:285`, `gradio_handler.py:108`), `zip_ref.extractall` (`bot_classes.py:446`), `analyze_image`/`apply_corrections` (`image_editor.py:500-503`), Whisper `model.transcribe` via `to_thread` (`main.py:573`, `350-355`), Gemini sync SDK via `to_thread` (`model_manager.py:234-236`, `utils.py:233-244`).
- Still blocking in async: `os.path/open/shutil/os.walk` in `_process_multipart_archive`/`_extract_and_queue_zip` (`bot_classes.py:404-467`), `open/write` transcript/summary files in `_process_transcript_job` (`main.py:582,608,622`), `cv2` inside `to_thread` is fine but `is_backlight`/`gray_world_wb` allocate full-res float32 copies (see 2.5).
- Fix: wrap file-walk/move loop in `to_thread` for large ZIPs, or accept with `noqa: ASYNC240/ASYNC230` + comment. Do not micro-opt before correctness fixes.

## 2.2 Security, secrets, authz, injection, archives

### S1. `CallbackQueryHandler` has no chat filter — P0 authz bypass
- `main.py:866` defines `chat_filter = filters.Chat(chat_id=TELEGRAM_CHAT_ID)`. Applied to `CommandHandler` (`main.py:869-871`) and `MessageHandler` (`main.py:873`), but `CallbackQueryHandler(button_callback)` at `main.py:872` has no filter.
- `button_callback` (`main.py:748-786`) handles `shutdown_bot`, `cancel_*`, `extend_idle`, `view_cancel_jobs` with no `query.from_user` / `query.message.chat_id` check. Any user who can see/reply to bot messages (group members if `TELEGRAM_CHAT_ID` is a group, or anyone if bot is discoverable) can shut down bot or cancel jobs. `shutdown_bot` at `main.py:759-761` only asks for button press, no confirm, no allowlist.
- Fix: add `filters=chat_filter` or manual `if query.message.chat_id != TELEGRAM_CHAT_ID: answer denied + return`. Add second confirm step for `shutdown_bot` (`Confirm shutdown? Yes/No`). Log `query.from_user.id` on shutdown/cancel.

### S2. `GITHUB_TOKEN` in logs and process list — P0 secret exposure
- `runner.py:37-39` `run_command()` prints `Executing: {cmd}`. Clone path builds `clone_url` with token embedded (`runner.py:188-193`: `clone_url.replace("https://", f"https://{token}@")`) then `run_command(f"git clone ... {clone_url}")` (`runner.py:193`). Token appears in stdout logs (persisted in Colab/Kaggle output) and in `ps aux` via `shell=True` + `os.system`.
- Same pattern for `git fetch/reset` via `os.system` with interpolated `branch` (`runner.py:179-185`); branch from `HEADLINEBOT_VERSION` env, low risk but shell-injection surface.
- Fix: use `subprocess.run([...], shell=False)`, pass token via `http.extraHeader` (`GIT_HTTP_EXTRAHEADER=Authorization: Bearer ...`) or `GIT_ASKPASS`, never log full command. Redact helper `redact(url)`.

### S3. Markdown injection via filenames/errors — P1
- User-controlled strings interpolated into `ParseMode.MARKDOWN` without escaping: `job.original_filename` (`main.py:589,679,704,733,735`, `bot_classes.py:226,336`), `job_name` (`main.py:773`), `str(error)` (`main.py:679,920,926`), `base_name`/`zip_name` (`bot_classes.py:383,386,411,423`), `diagnosis` caption (`main.py:546`).
- Filename containing `` ` ``, `*`, `_`, `[` breaks parse (`BadRequest: can't parse entities`) and can spoof messages. `global_error_handler` reply at `main.py:920` echoes raw exception (paths, model names) to chat.
- Fix: use `telegram.helpers.escape_markdown(text, version=1)` for all user-controlled interpolations, or switch user-echo messages to no parse mode. Truncate exceptions to 200 chars, strip absolute paths (`RUN_DIR`, home) before sending.

### S4. Zip Slip / Tar Slip — P0 (Telegram ZIP path exploitable)
- `_extract_and_queue_zip()` (`bot_classes.py:434-467`): `zip_ref.extractall(extract_dir)` with no member validation. `file_list` filter (`bot_classes.py:440`) only skips `__MACOSX`/dotfiles/dirs, does not reject `../`, absolute `/tmp/...`, or symlink entries. Malicious ZIP from Telegram (anyone passing `chat_filter`) can write outside `extract_dir`.
- `runner.download_repo_fallback()` (`runner.py:117-118`): `zf.extractall(".")` on remote GitHub ZIP (trusted origin, lower risk, still should validate).
- `colab/bootstrap.py:63-64`: `tarfile.open(...); tf.extractall(RUN_DIR)` with no `filter="data"` (Python 3.10 default is no filter; 3.14 warns). `hb.tar.gz` is self-built, low risk, but should harden.
- Fix: validate each `ZipInfo.filename`: reject absolute, `..` in `Path.parts`, symlinks (`is_symlink()`), device nodes; enforce size cap (sum uncompressed < e.g. 2GB) before extract. For tar: `tf.extractall(RUN_DIR, filter="data")` with fallback for 3.10, or manual member check.

### S5. Gemini remote file retention + privacy — P1
- `transcribe_with_gemini()` (`headlinebot/utils.py:230-252`) uploads via `files.upload`, polls until `ACTIVE`, transcribes, returns text, but never calls `files.delete`. Every transcription leaves remote object in Gemini File API, consuming quota and retaining journalist source audio.
- No `finally: delete` even on failure. No log of remote `audio_file.name` for manual cleanup.
- Fix: `try/finally: gemini_client.files.delete(name=audio_file.name)` after successful transcribe (or after all retries). Log deletion. Document retention policy for journalists.

### S6. Secrets handling notes (mostly correct, two tweaks) — P1
- Good: `secrets.load_infisical_secrets()` (`secrets.py:95-120`) prints only count + key names (`secrets.py:118-119`), never values. `bootstrap.py:82-88` checks names only. `.env` gitignored (`git check-ignore` confirms `.env` ignored, `report.md` untracked as expected).
- Issue 1: `get_infisical_credentials()` (`secrets.py:23-64`) swallows ALL exceptions and falls back to `os.environ`, masking Colab `userdata` permission errors. Double-called in `load_all_secrets()` (`secrets.py:131` then `100`), doubling latency.
- Issue 2: `colab-run.sh` uploads `.env` in clear to VM, no `chmod 600` check, no warning about shell history. `bootstrap.py` loads `.env` via `setdefault` (`bootstrap.py:71-72`), so stale env wins over `.env` — surprising precedence.
- Fix: cache credentials per process, log which source was used (`kaggle/colab/env`, never values), `chmod 600 .env`, document `setdefault` vs override precedence.

## 2.3 Lifecycle, startup, GPU/VRAM, disk

### L1. GPU detection mismatch can select wrong mode — P1
- `agent.md` says `torch.cuda`, code uses `nvidia-smi` (`start.py:8-14`). `nvidia-smi` present + CPU-only `torch` → `MODE='WHISPER'` (`start.py:22`), then `initialize_models_background()` detects `not torch.cuda.is_available()` and falls back to `device='cpu'` (`main.py:225-227`) but stays in WHISPER mode with `compute_type=int8` on CPU. `large-v2` on CPU is UNVERIFIED but expected to be very slow / OOM for long files.
- Fix: decide `MODE` after `torch.cuda.is_available()` check when torch present, or add `TRANSCRIPTION_MODE=auto` that prefers WHISPER only if both `nvidia-smi` AND `torch.cuda` true. Log both signals.

### L2. Background pip install races with polling — P1
- WHISPER mode with missing `torch`/`faster-whisper` triggers `uv pip install --system -r requirements.txt` inside `initialize_models_background()` (`main.py:250-255`) while bot already polls. No lock prevents `queue_processor` from starting Whisper jobs mid-install (mitigated because `models_ready_event` not set until load, but Gemini jobs could already run in fallback path). Disk/CPU contention, partial-install import flakiness.
- Fix: install before `run_polling`, or set `models_ready_event` only after install+load, and reject new jobs with `⏳ Installing dependencies, try in 2 min` during install window.

### L3. Whisper download has no integrity check — P1
- Hardcoded `_files = ["config.json","model.bin","tokenizer.json","vocabulary.txt"]` (`main.py:296`), `_repo` special-cased for `large-v2` (`main.py:298`). Other `MODEL_SIZE` values may need different manifests. `.part` + `os.rename` (`main.py:321,329`) with no checksum/size verification, no resume, `os.path.exists` skip assumes complete (`main.py:310-311`) — truncated previous download is reused forever.
- Progress log `if _pct % 20 == 0` (`main.py:327-328`) spams many lines per bucket (every 8MB chunk that lands exactly on 0/20/40/60/80%).
- Fix: verify `content-length` vs actual size, store `.sha256` or at least size file, re-download on mismatch. Throttle progress logs (e.g. every 10% edge-triggered).

### L4. Startup message + runtime teardown ordering — P2
- `post_init` sends startup message (`main.py:847-854`) before models ready, edits later (`main.py:445-481`). `BadRequest` on edit (message deleted, too old) only logged.
- `perform_shutdown` notifies then `application.stop()` immediately (`main.py:179-189`); notification may not flush before `runtime.unassign()`/`os._exit`. Add `await asyncio.sleep(1)` after notify (best-effort flush) before stop/unassign.
- `__main__` safety net (`main.py:952-956`) calls `runtime.unassign()` even after orderly `perform_shutdown` already did — double unassign harmless but noisy. Guard with `SHUTDOWN_IN_PROGRESS`.

### L5. CLI IN-PLACE silently ignores version switch — P2
- `runner.py:175-176`: if `is_repo_checkout()` true (CLI tarball), git steps skipped entirely. `HEADLINEBOT_VERSION`/`HEADLINEBOT_BRANCH` set (`runner.py:136-137`) but branch never checked out. User passing `--version beta` on existing `hb-run` gets prod code with beta env. At least log `IN-PLACE sha` (`git rev-parse --short HEAD` if `.git` present, else tarball mtime) and warn on mismatch.

## 2.4 Error handling, observability, logging

### E1. `Forbidden` must not be transient; `RetryAfter` must honor delay — P0
- `transient_errors` tuple (`main.py:887-899`) includes `'RetryAfter'` and `'Forbidden'`. `Forbidden` (bot blocked, kicked, deactivated) never recovers by retry; current code retries twice then logs `network may be unstable` and continues (`main.py:901-912`), hiding a fatal auth state.
- `RetryAfter` carries `retry_after` seconds; code ignores it, retries immediately up to 2x, guaranteeing second rate-limit.
- `_transient_error_counts` (`main.py:877,903-915`) never expires: counts persist for process lifetime, cleared only on non-transient error. Two isolated timeouts hours apart count as 2/2 then reset — misleading.
- Fix: remove `Forbidden` from transient, treat as fatal (notify + shutdown). For `RetryAfter`, `await asyncio.sleep(context.error.retry_after or 30)`. Use timestamped window (e.g. 5 min) for transient counts, or delegate to PTB built-in retry and only log.

### E2. Single per-update error can kill bot — P0
- `global_error_handler` else-branch (`main.py:914-926`) does `await perform_shutdown(f"Application Error: {error}")` for ANY non-transient error, including user-triggered `BadRequest` from Markdown injection (S3), `File too large` edge, or single-job ffmpeg failure bubbling to handler.
- Expected: per-update errors reply + continue; shutdown only for startup/init failures (`initialize_models_background` already calls `perform_shutdown("AI Model Loading Failed")` at `main.py:406` — correct scope).
- Fix: remove `perform_shutdown` from `global_error_handler` default path. Shutdown only on explicit allowlist (`MemoryError`, `SystemExit`, init failures). Add counter: shutdown after N critical errors in M minutes, not one.

### E3. Logs are stdout-only, unbounded, mixed levels — P1
- `log()` (`headlinebot/utils.py:32-40`) prints `[HH:MM:SS] [+Rm SSs] [CATEGORY] msg` to stdout; `bot_classes` mixes `print(..., file=sys.stderr)` (`bot_classes.py:317,428`), `print` for lifecycle (`bot_classes.py:274,373,422`). `bootstrap.py` opens `bot.log` append without rotation (`bootstrap.py:100-104`); long Kaggle 9h run with per-chunk Whisper logs grows without bound. No log level env, no JSON option for ingestion.
- `queue_processor` heartbeat (`main.py:644-650`) computes `elapsed` dead var, logs only `Queue`+`Status` — missing uptime, memory (`psutil` optional), disk free for `uploads/`, worker state.
- Fix: standardize on `log()`, add `LOG_LEVEL` env, rotate `bot.log` (e.g. 10MB × 3), enrich heartbeat with `get_runtime()`, `shutil.disk_usage(UPLOAD_FOLDER)`, queue depth. Keep stdout for Colab (unbuffered already via `PYTHONUNBUFFERED` in `runner.py:23`).

## 2.5 Perf, VRAM, disk (UNVERIFIED estimates — needs GPU run)

- Whisper `large-v2` + `beam_size=10` (`config.py:28`) + `patience=2.0` (`config.py:33`) is accuracy-max, speed-min. On T4 UNVERIFIED estimate: real-time factor ~0.2-0.4x for float16, worse for int8 CPU. Default `BEAM_SIZE=10` doubles latency vs `5` for marginal WER gain on clean interview audio. Recommend `BEAM_SIZE=5` default, `10` opt-in via env, document tradeoff.
- `compute_type` logic (`main.py:283-292`): `float16` on cuda, `int8` on cpu, `USE_FP16` override naming confusing (Phase 1). No `int8_float16` option despite `config.py:23` comment mentioning it. VRAM UNVERIFIED: `large-v2` float16 ~4-5GB + overhead fits T4 16GB, but concurrent image OpenCV + Gradio share same VM memory — monitor.
- Gemini poll (`utils.py:240-252`) + `try_model_chain` timeout 120s per model (`model_manager.py:234-236`) with `max_retries=2` and full chain (primary + N fallbacks) can hold worker 10+ minutes per file if quota exhausted. Add per-job deadline (e.g. 15 min) with explicit `failed-timeout` status instead of indefinite chain walk.
- Image: thumbnail 768px for LLM (`image_editor.py:166-171`, quality 82) is good cost control. `apply_corrections` full-res float32 pipeline (`image_editor.py:390-469`) allocates multiple H×W×3 float32 temporaries + `norm_original` copy; 50MP phone photo UNVERIFIED ~600MB transient — cap input to e.g. 24MP or tile clarity/sharpness passes. `JPEG_QUALITY=95` (`config.py:85`) large output for Telegram (recompressed anyway) — `92` sufficient.
- Disk: `uploads/`, `transcripts/`, `edited_images/`, `~/.cache/whisper_models/` never pruned except per-job delete. Failed/cancelled ZIP parts, `.part` fragments, `combined_*.zip` on exception path may leak (see C6). Add startup janitor: delete `uploads/*` older than 24h, `.part` older than 1h, `extract_*` dirs.
- Network: HF download chunk 8MB (`main.py:322`), no bandwidth cap — fine on Colab, but no resume.

## 2.6 Deps, supply chain, CI (safe-run evidence)

- Unpinned: `ffmpeg-python, faster-whisper, google-genai, nest_asyncio, opencv-python-headless, Pillow, python-telegram-bot, requests, tqdm, werkzeug, more-itertools` (`requirements.txt`), only `gradio>=4.0.0, httpx>=0.28.1` have lower bounds. Safe-run `pip index versions faster-whisper` shows many releases (1.2.1 latest seen); unpinned means Colab today vs Kaggle tomorrow diverge. `python-telegram-bot` major bump changes `Application`/`HTTPXRequest` API — highest breakage risk with `Update.ALL_TYPES` (`main.py:935`) + `HTTPXRequest` tuning (`main.py:798-804`).
- Possibly unused: `more-itertools`, `tqdm` have zero `rg ^import` hits in own code (transitive via `faster-whisper`/`gradio` likely). `httpx` only indirect via `telegram.request`. Either pin as transitive with comment or remove and let solver pull.
- `requirements_cpu.txt` ultra-light omits `requests` (needed by `secrets.py:19`), `google-genai` (lazy import at `main.py:363,394` — fails only when Gemini path hit, confusing late failure), `Pillow/numpy/opencv` (needed at top-level `image_editor` import). See Phase 1 F3 — still open.
- `pyproject.toml` keeps `F401` ignored, hiding unused-import drift. CI (`.github/workflows/ci.yml`) still installs `flake8` and checks `requirements_local.txt` (missing) instead of `ruff` + real requirements. Net effect: CI green while `ruff` I001 fails locally (safe-run confirms 2x I001 remain).
- `werkzeug` only for `secure_filename` (`bot_classes.py:18`, `main.py:38`). Acceptable, but pin major to avoid Flask-ecosystem breakage.
- Fix: add `requirements.lock` or `pip-compile` with hashes for prod GPU image, keep `requirements*.txt` as loose direct deps with `>=lower,<next-major`. Fix CI to `pip install -r requirements_cpu.txt && ruff check . && python -m compileall -q .`. Remove `F401` ignore or scope per-line `noqa: F401 # platform probe`.

## Phase 2 prioritized fixes (append to Phase 1 F1–F5)

- [ ] **P2-C1.** Defer `models_ready_event.set()` until Gemini ready; never write error-string as transcript (return `failed`).
- [ ] **P2-S1.** Add `chat_filter` to `CallbackQueryHandler` + sender check + confirm for `shutdown_bot`.
- [ ] **P2-S2.** Redact token from logs/`ps` (header auth, list-form subprocess).
- [ ] **P2-S4.** Validate ZIP/TAR members (no `..`/absolute/symlink, size cap, `filter="data"`).
- [ ] **P2-E1/E2.** Fix transient list (`Forbidden` fatal, honor `RetryAfter`), remove shutdown-on-single-update-error.
- [ ] **P2-S5.** Delete Gemini remote file in `finally`.
- [ ] **P2-C4.** Idempotent shutdown with task cancellation + `shutdown_gradio()` + flush delay.
- [ ] **P2-C5/C6.** Fix Gradio reply-to + Future handling or delete Gradio path; cap multipart dict + cancel timers on shutdown.
- [ ] **P2-L1/L3.** Fix GPU-mode decision + Whisper download integrity (size/checksum, throttled logs).
- [ ] **P2-D1.** Pin deps, fix CPU requirements, fix CI to ruff, remove `F401` ignore.

## Phase 2 verification (reproducible, safe, no secrets)

```bash
python3 -m compileall -q .  # must exit 0
python3 -m ruff check . --output-format=concise
rg -n "CallbackQueryHandler|filters\.Chat|chat_filter" --glob '*.py' .
rg -n "os\.system|shell=True|os\._exit|extractall|ZipFile|secure_filename" --glob '*.py' --glob '*.sh' .
rg -n "models_ready_event\.|job_queue\.(put|get|qsize|task_done)|SHUTDOWN_IN_PROGRESS|shutdown_imminent|perform_shutdown" --glob '*.py' .
rg -n "timeout=|max_retries|max_polls|RetryAfter|Forbidden" --glob '*.py' .
git status --porcelain; git check-ignore -v .env report.md
pip index versions faster-whisper  # read-only version check, no install
```

## Phase 2 open questions / UNVERIFIED

- VRAM/latency numbers are UNVERIFIED without T4 run (beam 10 vs 5, float16 vs int8, 2h audio). Need throwaway Colab timing before changing defaults.
- Telegram `reply_to_message_id=0` behavior for Gradio jobs UNVERIFIED — confirm `BadRequest` text before fixing message-id logic.
- PTB `application.stop()` vs `updater.stop()+shutdown()` ordering UNVERIFIED for installed PTB version (unpinned) — verify against `pip show python-telegram-bot` in target env.
- Gemini File API quota/retention policy for project UNVERIFIED — confirm delete permission and retention need with data owner (journalist source protection).
- Whether `TELEGRAM_CHAT_ID` is single user vs group determines S1 severity — confirm chat type before choosing allowlist model.

