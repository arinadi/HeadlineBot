# HeadlineBot - Agent Context

> **Role**: Act as an Equal Pair Programmer. Maintain consistent coding standards and structures.

## Project Overview
HeadlineBot is a Telegram bot for journalists, run on **Google Colab**, **Kaggle**, or locally. It does:
1.  **Transcription**: `faster-whisper` on GPU (WHISPER mode) or the **Gemini File API** on CPU (GEMINI mode).
2.  **Summary & Retouch**: Gemma/Gemini write an Indonesian journalist summary (`SM_`) and, for Whisper output, a cleaned-up transcript (`RT_`).
3.  **Photo Color Correction**: Gemma classifies the photo's condition, fine-tunes that condition's preset, and OpenCV applies it.
4.  **Archives**: ZIP and multi-part ZIP (`.zip.001`, ...) uploads are combined, safely extracted and queued.

Items 2 and 3 run only when `ENABLE_GEMINI_FEATURES=true` and `GEMINI_API_KEY` is set (off by default; photos are then returned unchanged).

## Architecture
-   **Launch chain**: README notebook cell (loads Infisical secrets) → `runner.py` (clone/update repo, `pip install -r requirements_cpu.txt`) → `start.py` → `main.py`. The colab CLI path is `colab/colab-run.sh` → `colab/bootstrap.py` → `start.py`.
-   **Mode**: `start.py` runs `nvidia-smi`; GPU found → `TRANSCRIPTION_MODE=WHISPER`, else `GEMINI`. In WHISPER mode `main.py` installs `requirements.txt` in the background and falls back to GEMINI if Whisper can't load.
-   **Versions**: `HEADLINEBOT_VERSION=prod` runs branch `main`, `beta` runs branch `beta`.
-   **Async**: `python-telegram-bot` 22 (`Application.run_polling`, which is synchronous and owns the event loop). One worker (`queue_processor`) handles jobs one at a time.

## Key Files
| File | Purpose |
| :--- | :--- |
| `runner.py` | Notebook entry point. Must stay self-contained: it runs before the repo exists. |
| `start.py` | GPU detection and launcher for `main.py`. |
| `main.py` | Telegram handlers, job worker, model loading, shutdown. |
| `headlinebot/config.py` | Secrets and all settings, read from environment variables. |
| `headlinebot/bot_classes.py` | `Job`, `JobManager`, `IdleMonitor`, `FilesHandler`, `extract_zip_safely`. |
| `headlinebot/utils.py` | Logging, Gemini transcription/summary/retouch, Markdown helpers. |
| `headlinebot/model_manager.py` | Discovers available Gemini/Gemma models and builds fallback chains. |
| `headlinebot/image_editor.py` | Two-pass photo analysis + OpenCV correction pipeline. |
| `headlinebot/secrets.py` | Infisical REST secret loader. |
| `presets.json` | Per-condition base presets and non-negotiable parameter locks. |
| `tests/` | pytest suite; `tests/fakes.py` holds stand-ins for Gemini and Telegram. |

## Critical Workflows

### 1. Startup
-   `post_init` starts the worker, background model loading and the idle monitor, then sends the startup message (its 🔌 button asks for confirmation before shutting down).
-   Idle monitor: first alert, final warning, then shutdown after `IDLE_*_MINUTES`; all three are 5x longer in GEMINI mode.

### 2. Transcription Pipeline
1.  **Receive**: `FilesHandler` checks the size limit; GEMINI mode also rejects files over 20 minutes.
2.  **Transcribe**: WHISPER mode runs `faster-whisper` locally; GEMINI mode uploads to the Gemini File API (the upload is deleted afterwards). Failures raise and are reported to the user as "Failed".
3.  **Result**: "Done" message + `TS_...` file.
4.  **AI (optional)**: `SM_...` summary and, in WHISPER mode, `RT_...` retouch, in parallel.
5.  **Cleanup**: local files removed.

### 3. Photo Color Correction Pipeline
1.  **Classify**: a 768px thumbnail goes to Gemma, which returns one condition code (e.g. `BACKLIGHT`).
2.  **Fine-tune**: Gemma adjusts that condition's preset from `presets.json`; the parameter locks are then enforced in code.
3.  **Process** (OpenCV): Gray World white balance (skipped for backlight), warmth/tint, brightness, contrast (tanh S-curve LUT), highlights/shadows, blacks/whites, saturation/vibrance, clarity/sharpness.
4.  **Quality Guard**: if the result is blown out or flat, the original is sent instead.

## Configuration (Environment Variables)
| Variable | Description | Default |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Bot token | **Required** |
| `TELEGRAM_CHAT_ID` | The only chat the bot serves | **Required** |
| `GEMINI_API_KEY` | Google AI Studio key (GEMINI mode, AI features) | optional |
| `ENABLE_GEMINI_FEATURES` | Summary, retouch, photo correction | `false` |
| `MODEL_SIZE` | Whisper model size | `large-v2` |
| `USE_FP16` | Whisper compute type: `auto`, `float16`, `int8`, `float32` | `auto` |
| `BOT_FILESIZE_LIMIT` | Max MB per file | `20` |
| `IDLE_SHUTDOWN_MINUTES` | Idle time before shutdown | `10` (`5` on beta) |
| `GEMMA_MODEL` | Gemma model for photo analysis | `models/gemma-4-26b-a4b-it` |
| `JPEG_QUALITY` | Output quality for edited photos | `95` |

See `headlinebot/config.py` for the Whisper decoding and VAD settings.

## Development Rules
-   **Language**: English for code comments and this file; the README is in Indonesian.
-   **Verification**: `ruff check .`, `python -m compileall -q .` and `pytest -q` must pass (CI runs them on Python 3.12).
-   **Branches**: work lands on `beta`, is tested on Colab with version `beta`, then `main` is fast-forwarded.
