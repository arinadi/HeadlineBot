# 🚀 Run Transcription Bot (Telegram Version - Modular)
# ------------------------------------------------------------------------------
# SECTION 1: CONFIGURATION AND SECRETS
# ------------------------------------------------------------------------------

# 🚀 Run Transcription Bot (Telegram Version - Modular)
# ------------------------------------------------------------------------------
# SECTION 1: IMPORT & CONFIGURATION
# ------------------------------------------------------------------------------

import asyncio
import gc
import os
import sys
import time
import uuid

from headlinebot import config
from headlinebot.bot_classes import FilesHandler, IdleMonitor, Job, JobManager
from headlinebot.config import Config

# NOTE: edit_image (cv2/numpy/PIL) is lazy-imported inside _process_image_job
# so CPU boot with requirements_cpu.txt does not require heavy deps at import.
from headlinebot.model_manager import discover_models
from headlinebot.utils import format_duration, get_runtime, log, retouch_transcript, set_model_chains, summarize_text

# --- Transcription Mode ---
MODE = os.getenv('TRANSCRIPTION_MODE', 'GEMINI')

# --- External Libraries (Core) ---
try:
    import nest_asyncio
    import telegram
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.constants import ParseMode
    from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
    from telegram.request import HTTPXRequest
    from werkzeug.utils import secure_filename
except ImportError as e:
    sys.exit(f"❌ Critical Dependency Missing: {e}\nPlease run: pip install -r requirements_cpu.txt")

GRADIO_AVAILABLE = False
gradio_handler = None
model = None
gemini_client = None

# --- Secrets & Config Alias ---
TELEGRAM_BOT_TOKEN = config.TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID = config.TELEGRAM_CHAT_ID
GEMINI_API_KEY = config.GEMINI_API_KEY

# Config Shortcuts
WHISPER_MODEL = Config.WHISPER_MODEL
WHISPER_PRECISION = Config.WHISPER_PRECISION
WHISPER_BEAM_SIZE = Config.WHISPER_BEAM_SIZE
WHISPER_PATIENCE = Config.WHISPER_PATIENCE
WHISPER_TEMPERATURE = Config.WHISPER_TEMPERATURE
WHISPER_REPETITION_PENALTY = Config.WHISPER_REPETITION_PENALTY
WHISPER_NO_REPEAT_NGRAM_SIZE = Config.WHISPER_NO_REPEAT_NGRAM_SIZE
VAD_FILTER = Config.VAD_FILTER
VAD_THRESHOLD = Config.VAD_THRESHOLD
VAD_MIN_SPEECH_DURATION_MS = Config.VAD_MIN_SPEECH_DURATION_MS
VAD_MIN_SILENCE_DURATION_MS = Config.VAD_MIN_SILENCE_DURATION_MS
VAD_SPEECH_PAD_MS = Config.VAD_SPEECH_PAD_MS
BOT_FILESIZE_LIMIT = Config.BOT_FILESIZE_LIMIT
ENABLE_IDLE_MONITOR = Config.ENABLE_IDLE_MONITOR
IDLE_FIRST_ALERT_MINUTES = Config.IDLE_FIRST_ALERT_MINUTES
IDLE_FINAL_WARNING_MINUTES = Config.IDLE_FINAL_WARNING_MINUTES
IDLE_SHUTDOWN_MINUTES = Config.IDLE_SHUTDOWN_MINUTES

# Detect Runtime Environment (Kaggle > Colab > Local)
IS_COLAB = False
IS_KAGGLE = False

try:
    from kaggle_secrets import UserSecretsClient  # noqa: F401  # availability probe
    IS_KAGGLE = True
    class KaggleRuntime:
        def unassign(self): print("🔌 Kaggle: no auto-shutdown (stop notebook manually)")
    runtime = KaggleRuntime()
except ImportError:
    try:
        from google.colab import runtime
        IS_COLAB = True
    except ImportError:
        class MockRuntime:
            def unassign(self): print("🔌 Local Runtime Shutdown Executed")
        runtime = MockRuntime()

# Validation
if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Core secrets (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) are missing.")

if not GEMINI_API_KEY:
    print("⚠️ WARNING: GEMINI_API_KEY not set. Summarization features will be disabled.")

# Constants
TRANSCRIPT_FILENAME_PREFIX = "TS"
SUMMARY_FILENAME_PREFIX = "SM"
RETOUCH_FILENAME_PREFIX = "RT"
IMAGE_OUTPUT_FOLDER = 'edited_images'
os.makedirs(IMAGE_OUTPUT_FOLDER, exist_ok=True)

# ------------------------------------------------------------------------------
# SECTION 2: ENVIRONMENT SETUP
# ------------------------------------------------------------------------------

nest_asyncio.apply()

# --- Compatibility Patch for nest_asyncio and Uvicorn ---
# Some versions of uvicorn (used by Gradio) call asyncio.run(..., loop_factory=...)
# nest_asyncio patches asyncio.run but doesn't always support loop_factory.
_orig_run = asyncio.run
def _patched_run(main, *, debug=None, loop_factory=None):
    try:
        if loop_factory is not None:
            return _orig_run(main, debug=debug)
        return _orig_run(main, debug=debug)
    except TypeError:
        # Fallback for versions that don't support debug either
        return _orig_run(main)
asyncio.run = _patched_run

# --- Filesystem Setup ---
UPLOAD_FOLDER = 'uploads'
TRANSCRIPT_FOLDER = 'transcripts'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TRANSCRIPT_FOLDER, exist_ok=True)


def _janitor_uploads(max_age_hours: int = 24):
    """Delete orphan uploads/extract dirs/.part files older than cap (best-effort)."""
    try:
        now = time.time()
        for name in os.listdir(UPLOAD_FOLDER):
            path = os.path.join(UPLOAD_FOLDER, name)
            try:
                age_h = (now - os.path.getmtime(path)) / 3600
                if age_h < max_age_hours:
                    continue
                if os.path.isdir(path) and name.startswith("extract_"):
                    import shutil
                    shutil.rmtree(path, ignore_errors=True)
                    log("INIT", f"Janitor removed old {name}")
                elif os.path.isfile(path) and (name.endswith(".part") or ".zip." in name):
                    os.remove(path)
                    log("INIT", f"Janitor removed old {name}")
            except Exception:
                continue
    except Exception as e:
        log("ERROR", f"Janitor failed: {e}")


_janitor_uploads()

# ------------------------------------------------------------------------------
# SECTION 3: AI AND HARDWARE INITIALIZATION
# ------------------------------------------------------------------------------

# Initial hardware detection (proxy)
# start.py sets MODE='WHISPER' only if it detects a GPU via nvidia-smi
device = "cuda" if MODE == 'WHISPER' else "cpu"

# Global State
model = None
gemini_client = None
models_ready_event = asyncio.Event()
# NOTE: Do NOT pre-set event for GEMINI here. Worker must wait until
# initialize_models_background() finishes gemini_client + discover_models(),
# otherwise transcribe_with_gemini() returns error-string as transcript (C1).



# ------------------------------------------------------------------------------
# SECTION 5: GLOBAL OBJECTS & WORKER
# ------------------------------------------------------------------------------

# --- Global State Variables ---
application: Application | None = None
idle_monitor: IdleMonitor | None = None
job_manager: JobManager | None = None
files_handler: FilesHandler | None = None
SHUTDOWN_IN_PROGRESS = False
STARTUP_MESSAGE_ID: int | None = None

async def send_telegram_notification(app: Application, message: str):
    """Sends a formatted message to the designated admin chat."""
    try:
        await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log("ERROR", f"Telegram notification failed: {e}")

async def perform_shutdown(reason: str):
    """Notifies admins and stops the bot. On Colab/Kaggle, also unassigns runtime."""
    global SHUTDOWN_IN_PROGRESS
    if SHUTDOWN_IN_PROGRESS:
        return
    SHUTDOWN_IN_PROGRESS = True
    uptime_str = get_runtime()
    log("SHUTDOWN", f"Initiated. Reason: {reason}")

    # 1. Notify admin (best-effort flush before teardown)
    try:
        if application:
            await send_telegram_notification(application, f"🔌 *Shutdown*\nReason: `{reason}`\nUptime: `{uptime_str}`")
            log("SHUTDOWN", "Notification sent")
            await asyncio.sleep(1)
    except Exception as e:
        log("ERROR", f"Final notification failed: {e}")

    # 1b. Stop background tasks
    try:
        if idle_monitor and idle_monitor._task:
            idle_monitor.stop()
    except Exception as e:
        log("ERROR", f"Idle monitor stop failed: {e}")
    try:
        if files_handler is not None:
            try:
                files_handler.cancel_all_multipart()
            except Exception:
                pass
    except Exception as e:
        log("ERROR", f"Multipart cleanup failed: {e}")
    try:
        if gradio_handler is not None:
            try:
                from headlinebot.gradio_handler import shutdown_gradio
                await shutdown_gradio()
            except Exception:
                pass
    except Exception as e:
        log("ERROR", f"Gradio shutdown failed: {e}")

    # 2. Stop Telegram polling/updater in PTB order (Updater.stop -> stop -> shutdown).
    # From callback context prefer stop_running() which still runs post_stop/shutdown.
    try:
        if application:
            try:
                if application.updater:
                    await application.updater.stop()
            except Exception as e:
                log("ERROR", f"Updater stop failed: {e}")
            try:
                application.stop_running()
            except Exception:
                pass
            try:
                await application.stop()
            except Exception as e:
                log("ERROR", f"Application stop failed: {e}")
            try:
                await application.shutdown()
            except Exception as e:
                log("ERROR", f"Application shutdown failed: {e}")
            log("SHUTDOWN", "Polling stopped")
    except Exception as e:
        log("ERROR", f"Failed to stop polling: {e}")

    # 3. Platform-specific termination
    try:
        if IS_KAGGLE:
            # Kaggle has no runtime.unassign() — force-kill the process
            log("SHUTDOWN", "Kaggle: force exit (no auto-shutdown available)")
            os._exit(0)
        elif IS_COLAB:
            if runtime:
                runtime.unassign()
            log("SHUTDOWN", "Colab runtime unassigned")
        else:
            log("SHUTDOWN", "Local: process will exit naturally")
    except Exception as e:
        log("ERROR", f"Runtime shutdown failed: {e}")

async def initialize_models_background():
    """Loads Whisper (if in WHISPER mode) and initializes Gemini client."""
    global model, gemini_client, GRADIO_AVAILABLE, MODE, device, gradio_handler
    try:
        if SHUTDOWN_IN_PROGRESS: return

        # Acknowledge the kitchen is heating up
        kitchen_status = "🍳 *Wok is heating up...*" if MODE == 'WHISPER' else "🥪 *Preparing ingredients...*"
        await send_telegram_notification(application, f"{kitchen_status}\nHeadlineBot is ready to take orders. AI engine will be ready shortly.")

        if MODE == 'WHISPER':
            if SHUTDOWN_IN_PROGRESS: return
            log("INIT", "Checking ML dependencies...")
            try:
                import torch
                from faster_whisper import WhisperModel
                # Final hardware check now that torch is here
                if not torch.cuda.is_available():
                    device = "cpu"
                    log("INIT", "GPU detected by system but not accessible by Torch. Using CPU.")

                try:
                    from headlinebot import gradio_handler as _gh
                    gradio_handler = _gh
                    GRADIO_AVAILABLE = True
                except ImportError:
                    pass
            except ImportError:
                if SHUTDOWN_IN_PROGRESS: return
                log("INIT", "Heavy ML dependencies missing. Installing in background...")
                await send_telegram_notification(application, "📦 *Unpacking heavy equipment...*\nDownloading AI libraries (~1-2 mins). I'll let you know when the kitchen is fully open.")

                # 1. Install uv first (now in background)
                subprocess_uv = await asyncio.create_subprocess_exec(
                    "pip", "install", "uv", "-q",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await subprocess_uv.communicate()

                if SHUTDOWN_IN_PROGRESS: return

                # 2. Install full requirements using uv
                process = await asyncio.create_subprocess_exec(
                    "uv", "pip", "install", "--system", "-r", "requirements.txt",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()

                if SHUTDOWN_IN_PROGRESS: return

                if process.returncode != 0:
                    log("ERROR", f"Failed to install ML dependencies: {stderr.decode()}")
                    await send_telegram_notification(application, "❌ *Kitchen equipment failure.* Falling back to GEMINI (Cloud) mode.")
                    MODE = 'GEMINI'
                    os.environ['TRANSCRIPTION_MODE'] = 'GEMINI'
                else:
                    log("INIT", "ML dependencies installed successfully.")
                    import torch
                    from faster_whisper import WhisperModel
                    # Final hardware check after install
                    if not torch.cuda.is_available():
                        device = "cpu"
                    try:
                        from headlinebot import gradio_handler as _gh2
                        gradio_handler = _gh2
                        GRADIO_AVAILABLE = True
                    except ImportError:
                        pass

        if SHUTDOWN_IN_PROGRESS: return

        if MODE == 'WHISPER':
            import torch
            from faster_whisper import WhisperModel
            # Logic for compute_type
            compute_type = "float16" if device == "cuda" else "int8"

            # User override logic
            prec_cfg = str(WHISPER_PRECISION).lower()
            if prec_cfg == 'false' or prec_cfg == 'float32':
                compute_type = "float32"
            elif prec_cfg == 'float16':
                compute_type = "float16"
            elif prec_cfg == 'int8':
                compute_type = "int8"

            # Download model files via raw HTTP (bypass Xet which hangs on Colab)
            # CTranslate2 manifest (validated): config.json, preprocessor_config.json,
            # model.bin, tokenizer.json, vocabulary.* — probe existence per MODEL_SIZE.
            _candidates = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.txt", "vocabulary.json"]
            _repo = "Systran/faster-whisper-large-v2" if WHISPER_MODEL == "large-v2" else f"Systran/faster-whisper-{WHISPER_MODEL}"
            _local_dir = os.path.expanduser(f"~/.cache/whisper_models/{WHISPER_MODEL}")
            os.makedirs(_local_dir, exist_ok=True)

            import requests as _req
            hf_token = os.getenv("HF_TOKEN", "")
            _headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
            start_ts = time.time()

            # Probe which candidates exist (HEAD). Core files are required.
            _files: list[str] = []
            for _fname in sorted(_candidates):
                _dest_probe = os.path.join(_local_dir, _fname)
                if os.path.exists(_dest_probe) and os.path.getsize(_dest_probe) > 0:
                    _files.append(_fname)
                    continue
                try:
                    _head = await asyncio.to_thread(
                        _req.head,
                        f"https://huggingface.co/{_repo}/resolve/main/{_fname}",
                        headers=_headers, timeout=10,
                    )
                    if _head.status_code == 200:
                        _files.append(_fname)
                    else:
                        log("INIT", f"  Skip missing: {_fname} (HTTP {_head.status_code})")
                except Exception as _e:
                    # On probe failure, try download anyway for core files; skip optional vocab variants later on 404
                    log("INIT", f"  Probe failed for {_fname}: {_e} — will try download")
                    _files.append(_fname)
            for _core in ("config.json", "model.bin", "tokenizer.json"):
                if _core not in _files:
                    raise RuntimeError(f"Required model file missing in repo {_repo}: {_core}")
            log("INIT", f"Downloading {len(_files)} files for {WHISPER_MODEL} via raw HTTP...")

            _max_retries = 3
            for _fname in sorted(_files):
                _dest = os.path.join(_local_dir, _fname)
                # Reuse only non-empty complete files (size verified below on download)
                if os.path.exists(_dest) and os.path.getsize(_dest) > 0:
                    # Optional vocab variants may be stale; core files keep cache
                    if _fname.startswith("vocabulary"):
                        pass
                    else:
                        continue
                _url = f"https://huggingface.co/{_repo}/resolve/main/{_fname}"
                _downloaded = False
                _last_pct = -1
                for _attempt in range(1, _max_retries + 1):
                    try:
                        log("INIT", f"  Downloading: {_fname}" + (f" (attempt {_attempt}/{_max_retries})" if _attempt > 1 else ""))
                        _resp = await asyncio.to_thread(_req.get, _url, headers=_headers, stream=True, timeout=(10, 300))
                        if _resp.status_code == 404 and _fname.startswith("vocabulary"):
                            log("INIT", f"  Skip optional missing: {_fname}")
                            _downloaded = True
                            break
                        _resp.raise_for_status()
                        _total = int(_resp.headers.get("content-length", 0))
                        _downloaded_bytes = 0
                        with open(_dest + ".part", "wb") as _f:
                            for _chunk in _resp.iter_content(chunk_size=8*1024*1024):
                                if not _chunk:
                                    continue
                                _f.write(_chunk)
                                _downloaded_bytes += len(_chunk)
                                if _total:
                                    _pct = _downloaded_bytes * 100 // _total
                                    # Edge-triggered every 10% (not %20 spam)
                                    if _pct // 10 != _last_pct // 10:
                                        _last_pct = _pct
                                        log("INIT", f"    {_fname}: {_pct}%")
                        # Size integrity check
                        if _total and os.path.getsize(_dest + ".part") != _total:
                            raise OSError(f"Size mismatch for {_fname}: got {os.path.getsize(_dest + '.part')} expected {_total}")
                        if os.path.getsize(_dest + ".part") == 0:
                            raise OSError(f"Empty download for {_fname}")
                        os.rename(_dest + ".part", _dest)
                        _size_mb = os.path.getsize(_dest) / (1024*1024)
                        log("INIT", f"  Done: {_fname} ({_size_mb:.0f}MB)")
                        _downloaded = True
                        break
                    except Exception as _e:
                        log("INIT", f"  ⚠️ {_fname} attempt {_attempt}/{_max_retries} failed: {_e}")
                        # Clean partial download
                        _part = _dest + ".part"
                        if os.path.exists(_part):
                            try:
                                os.remove(_part)
                            except Exception:
                                pass
                        if _attempt < _max_retries:
                            _delay = 2 ** _attempt
                            log("INIT", f"  Retrying in {_delay}s...")
                            await asyncio.sleep(_delay)
                if not _downloaded:
                    raise RuntimeError(f"Failed to download {_fname} after {_max_retries} attempts")

            elapsed = time.time() - start_ts
            log("INIT", f"All {len(_files)} files ready in {elapsed:.0f}s")

            model = await asyncio.to_thread(
                WhisperModel,
                _local_dir,
                device=device,
                compute_type=compute_type
            )
            log("INIT", f"Whisper loaded ({compute_type})")

        if SHUTDOWN_IN_PROGRESS: return

        if GEMINI_API_KEY:
            log("INIT", "Initializing Gemini...")
            # Lazy load google-genai
            from google import genai
            gemini_client = genai.Client(api_key=GEMINI_API_KEY)
            log("INIT", "Gemini ready")

            # Discover available models
            model_chains = await discover_models(gemini_client)
            set_model_chains(model_chains)

        if SHUTDOWN_IN_PROGRESS: return

        models_ready_event.set()

        # NOTE: Gradio launch is owned by post_init() only (single site).
        # Do NOT schedule initialize_gradio_background() here (was double launch).

        # Update startup message
        await update_startup_message()
        await send_telegram_notification(application, "🛎️ *Kitchen is now open!* All AI systems are ready to process your orders.")

    except Exception as e:
        if SHUTDOWN_IN_PROGRESS: return
        log("ERROR", f"Initialization failed: {e}")
        if MODE == 'WHISPER':
            log("INIT", "Whisper unavailable, falling back to Gemini Cloud...")
            await send_telegram_notification(application, f"⚠️ *Whisper unavailable.* Falling back to Gemini Cloud.\nError: `{str(e)[:150]}`")
            MODE = 'GEMINI'
            os.environ['TRANSCRIPTION_MODE'] = 'GEMINI'
            device = "cpu"
            try:
                if GEMINI_API_KEY:
                    from google import genai
                    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
                    model_chains = await discover_models(gemini_client)
                    set_model_chains(model_chains)
                    log("INIT", "Gemini ready (fallback)")
                models_ready_event.set()
                await update_startup_message()
                await send_telegram_notification(application, "🛎️ *Kitchen is now open!* Running on Gemini Cloud.")
                return
            except Exception as e2:
                log("ERROR", f"Gemini fallback also failed: {e2}")
                await send_telegram_notification(application, f"❌ *FATAL:* Both Whisper & Gemini failed:\n`{str(e2)}`")
        await perform_shutdown("AI Model Loading Failed")


async def initialize_gradio_background():
    """Launches Gradio web server in background and notifies Telegram with pinned URL."""
    global gradio_handler
    if not GRADIO_AVAILABLE or not gradio_handler:
        log("GRADIO", "Not available, skipping")
        return

    try:
        log("GRADIO", "Starting web interface...")
        main_loop = asyncio.get_running_loop()
        gradio_handler.set_dependencies(job_manager, UPLOAD_FOLDER, main_loop)
        public_url = await gradio_handler.launch_gradio_async(share=True)

        if public_url:
            log("GRADIO", f"Online: {public_url}")
            # Update startup message with URL
            await update_startup_message(public_url)

            # Pin the startup message
            if STARTUP_MESSAGE_ID:
                try:
                    await application.bot.unpin_all_chat_messages(chat_id=TELEGRAM_CHAT_ID)
                    await application.bot.pin_chat_message(
                        chat_id=TELEGRAM_CHAT_ID,
                        message_id=STARTUP_MESSAGE_ID,
                        disable_notification=True
                    )
                except Exception:
                    pass
        else:
            log("GRADIO", "Started but no public URL")
    except Exception as e:
        log("ERROR", f"Gradio failed: {str(e)}")
        # Gradio failure is not fatal to the bot
        await send_telegram_notification(application, f"⚠️ *Web UI Warning:* Failed to start Gradio:\n`{str(e)}`")

async def update_startup_message(gradio_url: str = None):
    """Updates the persistent startup message with current status."""
    if not STARTUP_MESSAGE_ID:
        return

    ai_status = "✅ Kitchen Open" if models_ready_event.is_set() else "⏳ Preparing..."
    hardware_label = "NVIDIA GPU" if device == "cuda" else "Standard CPU"

    # If gradio_url is not passed, try to fetch it via helper (no private access)
    if not gradio_url and GRADIO_AVAILABLE and gradio_handler is not None:
        try:
            gradio_url = gradio_handler.get_share_url()
        except Exception:
            gradio_url = None

    gradio_text = f"🌐 *Web UI:* {gradio_url}\n" if gradio_url else ""

    msg_text = (
        f"📰 *Welcome to HeadlineBot*\n"
        f"Your AI assistant for front-line reporting. Send your files anytime.\n\n"
        f"🛠️ *Equipment:* `{hardware_label}`\n"
        f"🤖 *AI Engine:* `{'Gemini Cloud' if MODE == 'GEMINI' else WHISPER_MODEL}`\n"
        f"📢 *Status:* {ai_status}\n"
        f"{gradio_text}"
        f"📂 *Order Limit:* `{BOT_FILESIZE_LIMIT}MB` per file"
    )

    keyboard = [[InlineKeyboardButton("🔌 Close Restaurant", callback_data="shutdown_bot")]]

    try:
        await application.bot.edit_message_text(
            chat_id=TELEGRAM_CHAT_ID,
            message_id=STARTUP_MESSAGE_ID,
            text=msg_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        log("ERROR", f"Failed to update startup message: {e}")


def run_transcription_process(job: Job) -> tuple[str, str]:
    """Runs the blocking Whisper transcription in a separate thread."""
    # Note: This runs in a thread, so we use print directly (log_utils works here too)
    from headlinebot.utils import log
    log("WHISPER", f"[{job.job_id}] Transcribing {job.original_filename}...")

    transcribe_options = {
        "beam_size": WHISPER_BEAM_SIZE,
        "patience": WHISPER_PATIENCE,
        "temperature": WHISPER_TEMPERATURE,
        "repetition_penalty": WHISPER_REPETITION_PENALTY,
        "no_repeat_ngram_size": WHISPER_NO_REPEAT_NGRAM_SIZE
    }

    # Run transcription
    # VAD parameters from user research
    vad_parameters = dict(
        threshold=VAD_THRESHOLD,
        min_speech_duration_ms=VAD_MIN_SPEECH_DURATION_MS,
        min_silence_duration_ms=VAD_MIN_SILENCE_DURATION_MS,
        speech_pad_ms=VAD_SPEECH_PAD_MS
    )

    segments_generator, info = model.transcribe(
        job.local_filepath,
        vad_filter=VAD_FILTER,
        vad_parameters=vad_parameters,
        **transcribe_options
    )

    # Convert generator to list to ensure full processing
    segments = list(segments_generator)

    # Use native formatting (Raw segments from Whisper)
    from headlinebot.utils import format_transcription_native
    formatted_text = format_transcription_native(segments)


    log("WHISPER", f"[{job.job_id}] Done: {len(segments)} segments, lang={info.language} ({info.language_probability:.0%})")

    return formatted_text, info.language if info.language else 'N/A'

async def _process_image_job(job: Job, _start_time: float):
    """Process an image color correction job."""
    await application.bot.send_message(job.chat_id, f"🎨 Analyzing `{job.original_filename}`...", parse_mode=ParseMode.MARKDOWN, reply_to_message_id=job.message_id)

    # Generate output path
    base_name = os.path.splitext(job.original_filename)[0]
    ext = os.path.splitext(job.original_filename)[1].lower()
    if ext not in ('.jpg', '.jpeg'):
        ext = '.jpg'
    output_filename = f"edited_{base_name}{ext}"
    output_path = os.path.join(IMAGE_OUTPUT_FOLDER, f"{uuid.uuid4().hex}_{output_filename}")

    # Process (lazy import keeps CPU boot light)
    ENABLE_GEMINI = os.getenv('ENABLE_GEMINI_FEATURES', 'false').lower() == 'true'
    if gemini_client and ENABLE_GEMINI:
        try:
            from headlinebot.image_editor import edit_image
        except ImportError as e:
            log("ERROR", f"[{job.job_id}] Image deps missing: {e}")
            with open(job.local_filepath, 'rb') as img_file:
                await job._original_message.reply_photo(photo=img_file, caption="⚠️ Image deps missing. Original sent.")
            if os.path.exists(output_path):
                os.remove(output_path)
            return
        result = await edit_image(job.local_filepath, output_path, gemini_client)
        if result["status"] == "success":
            params = result["params"]
            diagnosis = params.get("description", "Color corrected")
            with open(output_path, 'rb') as img_file:
                await job._original_message.reply_photo(photo=img_file, caption=f"🎨 *{diagnosis}*")
            log("JOB", f"[{job.job_id}] Image edited: {diagnosis}")
        else:
            # Fallback: send original
            with open(job.local_filepath, 'rb') as img_file:
                await application.bot.reply_photo(job._original_message, photo=img_file, caption="⚠️ AI correction failed. Original sent.")
            log("ERROR", f"[{job.job_id}] Image edit failed: {result.get('error')}")
    else:
        # No Gemini — send original
        with open(job.local_filepath, 'rb') as img_file:
            await application.bot.reply_photo(job._original_message, photo=img_file, caption="⚠️ AI color correction unavailable (no GEMINI_API_KEY). Original sent.")

    # Cleanup output file
    if os.path.exists(output_path):
        os.remove(output_path)


async def _process_transcript_job(job: Job, start_time: float):
    """Process a transcription job (transcript + summary + retouch)."""
    duration_str = format_duration(job.audio_duration)
    await application.bot.send_message(job.chat_id, f"▶️ Processing `{job.original_filename}` ({duration_str})...", parse_mode=ParseMode.MARKDOWN, reply_to_message_id=job.message_id)

    # 1. Transcribe
    if MODE == 'GEMINI':
        from headlinebot.utils import transcribe_with_gemini
        if gemini_client is None:
            raise RuntimeError("Gemini client not initialized (missing GEMINI_API_KEY or discovery failed)")
        transcript_text, detected_language = await transcribe_with_gemini(job.local_filepath, gemini_client)
    else:
        if model is None:
            raise RuntimeError("Whisper model not loaded yet")
        transcript_text, detected_language = await asyncio.to_thread(run_transcription_process, job)

    if job.status == 'cancelled':
        raise asyncio.CancelledError("Job cancelled during transcription.")

    # Never persist error-strings as transcripts (C1). Fail job instead.
    if not transcript_text or transcript_text.lstrip().startswith("Error"):
        raise RuntimeError(f"Transcription failed: {transcript_text[:200]}")

    base_name = os.path.splitext(job.original_filename)[0]
    safe_name = secure_filename(base_name)[:50]
    ts_filename = f"{TRANSCRIPT_FILENAME_PREFIX}_({duration_str.replace(' ', '')})_{safe_name}.txt"
    ts_filepath = os.path.join(TRANSCRIPT_FOLDER, ts_filename)
    with open(ts_filepath, "w", encoding="utf-8") as f:
        f.write(transcript_text)

    # Send transcript
    processing_duration_str = format_duration(time.time() - start_time)
    log("JOB", f"[{job.job_id}] Transcription done in {processing_duration_str}")

    from headlinebot.utils import escape_md_v1 as _esc
    result_text = (f"✅ *Done!* `{_esc(job.original_filename)}`\n"
                   f"⏱️ {duration_str} audio → {processing_duration_str} process\n"
                   f"🌐 Lang: {detected_language.upper()}\n"
                   f"🤖 Generating AI Summary...")
    await application.bot.send_message(job.chat_id, result_text, parse_mode=ParseMode.MARKDOWN, reply_to_message_id=job.message_id)

    with open(ts_filepath, 'rb') as ts_file:
        await application.bot.send_document(job.chat_id, document=ts_file, filename=ts_filename, reply_to_message_id=job.message_id)

    # 2. AI Summary + Retouch — PARALLEL, send 1-by-1 as each succeeds
    ENABLE_GEMINI = os.getenv('ENABLE_GEMINI_FEATURES', 'false').lower() == 'true'
    if gemini_client and ENABLE_GEMINI:
        do_retouch = MODE == 'WHISPER'

        async def _run_and_send_summary():
            log("JOB", f"[{job.job_id}] Generating summary...")
            result = await summarize_text(transcript_text, gemini_client)
            if result:
                su_filename = f"{SUMMARY_FILENAME_PREFIX}_({duration_str.replace(' ', '')})_{safe_name}.txt"
                su_filepath = os.path.join(TRANSCRIPT_FOLDER, su_filename)
                with open(su_filepath, "w", encoding="utf-8") as f:
                    f.write(result)
                with open(su_filepath, 'rb') as su_file:
                    await application.bot.send_document(job.chat_id, document=su_file, filename=su_filename, reply_to_message_id=job.message_id)
                log("JOB", f"[{job.job_id}] Summary sent.")

        async def _run_and_send_retouch():
            if not do_retouch:
                return
            log("JOB", f"[{job.job_id}] Generating retouch...")
            result = await retouch_transcript(transcript_text, gemini_client)
            if result:
                rt_filename = f"{RETOUCH_FILENAME_PREFIX}_({duration_str.replace(' ', '')})_{safe_name}.txt"
                rt_filepath = os.path.join(TRANSCRIPT_FOLDER, rt_filename)
                with open(rt_filepath, "w", encoding="utf-8") as f:
                    f.write(result)
                with open(rt_filepath, 'rb') as rt_file:
                    await application.bot.send_document(job.chat_id, document=rt_file, filename=rt_filename, reply_to_message_id=job.message_id)
                log("JOB", f"[{job.job_id}] Retouch sent.")

        results = await asyncio.gather(_run_and_send_summary(), _run_and_send_retouch(), return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                log("ERROR", f"AI task failed: {r}")
                safe_r = _esc(str(r), limit=200)
                await application.bot.send_message(job.chat_id, f"⚠️ AI Failed: {safe_r}", reply_to_message_id=job.message_id)


async def queue_processor():
    """The main worker loop that processes jobs from the queue one by one."""
    log("WORKER", "Waiting for AI models...")
    await models_ready_event.wait()
    log("WORKER", "Models ready. Processing jobs...")
    last_heartbeat = time.time()
    while not SHUTDOWN_IN_PROGRESS:
        # Heartbeat every 60s — keeps Kaggle alive (prevents idle kill)
        if time.time() - last_heartbeat >= 60:
            uptime = get_runtime()
            qsize = job_manager.job_queue.qsize()
            processing = job_manager.currently_processing
            status = f"processing {processing.original_filename}" if processing else "idle"
            try:
                import shutil
                free_mb = shutil.disk_usage(UPLOAD_FOLDER).free // (1024 * 1024)
                disk = f" | DiskFree={free_mb}MB"
            except Exception:
                disk = ""
            log("HEARTBEAT", f"Uptime={uptime} | Queue={qsize} | Status={status}{disk}")
            last_heartbeat = time.time()

        try:
            job: Job = await asyncio.wait_for(job_manager.job_queue.get(), timeout=30)
        except asyncio.TimeoutError:
            continue  # Loop back to heartbeat check

        if job.status == 'cancelled':
            log("WORKER", f"[{job.job_id}] Skipped (cancelled)")
            if os.path.exists(job.local_filepath):
                os.remove(job.local_filepath)
            job_manager.job_queue.task_done()
            job_manager.complete_job(job.job_id)
            continue

        job_manager.set_processing_job(job)
        try:
            if job.job_type == "image":
                await _process_image_job(job, time.time())
            else:
                await _process_transcript_job(job, time.time())
            job.status = "completed"

        except asyncio.CancelledError as e:
            log("WORKER", f"[{job.job_id}] Aborted: {e}")
        except Exception as e:
            job.status = "failed"
            log("ERROR", f"[{job.job_id}] {e}")
            try:
                from headlinebot.utils import escape_md_v1
                safe_name = escape_md_v1(job.original_filename)
                safe_err = escape_md_v1(str(e), limit=200)
                await application.bot.send_message(job.chat_id, f"❌ *Failed:* `{safe_name}`\n`{safe_err}`", parse_mode=ParseMode.MARKDOWN, reply_to_message_id=job.message_id)
            except Exception:
                log("ERROR", f"[{job.job_id}] Failed to send error notification")
        finally:
            if os.path.exists(job.local_filepath):
                try:
                    os.remove(job.local_filepath)
                except Exception:
                    pass

            gc.collect()

            job_manager.job_queue.task_done()
            job_manager.complete_job(job.job_id)

# ------------------------------------------------------------------------------
# SECTION 6: TELEGRAM UI COMMANDS
# ------------------------------------------------------------------------------

async def get_status_text_and_keyboard():
    """Builds the dynamic status message text and keyboard."""
    processing_job = job_manager.currently_processing
    if processing_job:
        processing_line = f"👨‍🍳 *Currently Cooking:* `{processing_job.original_filename}`\n"
    else:
        processing_line = ""

    ai_status = "✅ Kitchen Ready" if models_ready_event.is_set() else "⏳ Preparing Kitchen"
    mode_label = "Gemini Cloud" if MODE == 'GEMINI' else f"Local {WHISPER_MODEL}"
    hardware_label = "NVIDIA GPU" if device == "cuda" else "Standard CPU"

    text = (
        f"📊 *Restaurant Status*\n"
        f"🛠️ *Equipment:* `{hardware_label}`\n"
        f"🤖 *AI Engine:* `{mode_label}`\n"
        f"{processing_line}"
        f"⏳ Uptime: `{get_runtime()}` | Queue: `{job_manager.job_queue.qsize()}`\n"
        f"🛎️ *AI Status:* {ai_status}"
    )
    keyboard = [[InlineKeyboardButton("📄 View Orders", callback_data="view_cancel_jobs"), InlineKeyboardButton("🔄", callback_data="refresh_status"), InlineKeyboardButton("🔌", callback_data="shutdown_bot")]]

    return text, InlineKeyboardMarkup(keyboard)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, reply_markup = await get_status_text_and_keyboard()
    await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    processing_job = job_manager.currently_processing
    queued_jobs = job_manager.get_queued_jobs()
    lines = ["📄 *Job Queue*\n"]
    if processing_job:
        lines.append(f"\n▶️ *Currently Processing*\n`{processing_job.original_filename}`\n(By: {processing_job.author_display_name})")
    if queued_jobs:
        queue_text = [f"*{i}.* `{job.original_filename}` (By: {job.author_display_name})" for i, job in enumerate(queued_jobs, 1)]
        lines.append(f"\n⏳ *In Queue ({len(queued_jobs)})*\n" + "\n".join(queue_text))
    elif not processing_job:
        lines.append("\nThe queue is empty.")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def extend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ENABLE_IDLE_MONITOR:
        await update.effective_message.reply_text("Idle monitor disabled.")
        return
    msg = "✅ +5m extended" if idle_monitor.extend_timer(5) else "ℹ️ Bot active, no timer."
    await update.effective_message.reply_text(msg)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    # Authz: CallbackQueryHandler takes no filters — enforce allowlist manually.
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id != TELEGRAM_CHAT_ID:
        try:
            await query.answer("Denied.", show_alert=True)
        except Exception:
            pass
        log("ERROR", f"Denied callback {data!r} from chat {chat_id} user {query.from_user.id if query.from_user else '?'}")
        return

    if data == "refresh_status":
        text, reply_markup = await get_status_text_and_keyboard()
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        except telegram.error.BadRequest:
            pass
    elif data == "shutdown_bot":
        user = query.from_user.first_name if query.from_user else "?"
        uid = query.from_user.id if query.from_user else "?"
        log("SHUTDOWN", f"Shutdown requested by {user} (id={uid}) — asking confirm")
        confirm_kb = [
            [InlineKeyboardButton("✅ Yes, shut down", callback_data="confirm_shutdown")],
            [InlineKeyboardButton("« Cancel", callback_data="refresh_status")],
        ]
        await query.edit_message_text(
            "🔴 *Shut down bot?* Confirm below.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(confirm_kb),
        )
    elif data == "confirm_shutdown":
        user = query.from_user.first_name if query.from_user else "?"
        uid = query.from_user.id if query.from_user else "?"
        log("SHUTDOWN", f"Shutdown confirmed by {user} (id={uid})")
        await query.edit_message_text("🔴 *MANUAL SHUTDOWN INITIATED...*", parse_mode=ParseMode.MARKDOWN)
        await perform_shutdown(f"Manual Shutdown by {user} (id={uid})")
    elif data == "view_cancel_jobs":
        queued_jobs = job_manager.get_queued_jobs()
        if not queued_jobs:
            await query.edit_message_text("The queue is empty.", reply_markup=None)
            return
        keyboard = [[InlineKeyboardButton(f"{job.original_filename[:40]}... (ID: {job.job_id})", callback_data=f"cancel_{job.job_id}")] for job in queued_jobs]
        keyboard.append([InlineKeyboardButton("« Back to Status", callback_data="refresh_status")])
        await query.edit_message_text("Select a job below to cancel it:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("cancel_"):
        job_id = data.split("_")[1]
        cancelled, job_name = await job_manager.cancel_job(job_id)
        try:
            from telegram.helpers import escape_markdown
            safe_name = escape_markdown(str(job_name), version=1)
        except Exception:
            safe_name = str(job_name).replace("`", "'")[:80]
        if cancelled:
            msg = f"✅ Job `{safe_name}` was cancelled."
        else:
            msg = "❌ Could not cancel job (already processing or unknown)."
        await query.edit_message_text(msg, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
    elif data == "extend_idle":
        # Rate limit check (5 minutes = 300 seconds)
        if time.time() - idle_monitor.last_extend_time < 300:
            await query.answer("⏳ Please wait 5 minutes before extending again.", show_alert=True)
            return

        if idle_monitor.extend_timer(5):
            idle_monitor.last_extend_time = time.time()
            new_text = f"✅ *Idle Extended*\nTimer added +5 minutes.\n_Action by {query.from_user.first_name}_"
            await query.edit_message_text(new_text, parse_mode=ParseMode.MARKDOWN)
        else:
            await query.edit_message_text("ℹ️ Bot is already active, no need to extend.", parse_mode=ParseMode.MARKDOWN)

# ------------------------------------------------------------------------------
# SECTION 7: MAIN ENTRY POINT
# ------------------------------------------------------------------------------

async def main():
    global application, idle_monitor, job_manager, files_handler

    print("🚀 Starting Main Application...")

    # Longer timeouts and connection pool for network resilience
    request = HTTPXRequest(
        read_timeout=60.0,
        connect_timeout=20.0,
        write_timeout=30.0,
        pool_timeout=30.0,
        connection_pool_size=8
    )

    if not TELEGRAM_BOT_TOKEN:
        sys.exit("❌ FATAL: No TELEGRAM_BOT_TOKEN found. Exiting.")

    async def post_init(application: Application):
        """Initializes background tasks after the application is ready."""
        log("INIT", "Running post-init tasks...")

        # Background Tasks - start AFTER bot is ready to receive
        application.create_task(queue_processor())
        application.create_task(initialize_models_background())

        # Start Gradio web interface (async, like AI models)
        if GRADIO_AVAILABLE:
            application.create_task(initialize_gradio_background())

        if ENABLE_IDLE_MONITOR:
            # CPU/Gemini Mode: 5x longer timeouts (effective, via IdleMonitor).
            if MODE == 'GEMINI':
                idle_monitor.set_effective_timeouts(
                    IDLE_FIRST_ALERT_MINUTES * 5,
                    IDLE_FINAL_WARNING_MINUTES * 5,
                    IDLE_SHUTDOWN_MINUTES * 5,
                )
                log("INIT", f"CPU Mode: Idle timers set to {IDLE_FIRST_ALERT_MINUTES * 5}/{IDLE_FINAL_WARNING_MINUTES * 5}/{IDLE_SHUTDOWN_MINUTES * 5}m")
            idle_monitor.start()

        # Send startup notification in background (non-blocking)
        hardware_label = "NVIDIA GPU" if device == "cuda" else "Standard CPU"
        startup_text = (
            f"📰 *Welcome to HeadlineBot*\n"
            f"Your AI assistant for front-line reporting. Send your files anytime.\n\n"
            f"🛠️ *Equipment:* `{hardware_label}`\n"
            f"🤖 *AI Engine:* `{'Gemini Cloud' if MODE == 'GEMINI' else WHISPER_MODEL}`\n"
            f"📢 *Status:* ⏳ Preparing...\n\n"
            f"📂 *Order Limit:* `{BOT_FILESIZE_LIMIT}MB` per file"
        )
        keyboard = [[InlineKeyboardButton("🔌 Close Restaurant", callback_data="shutdown_bot")]]

        msg = await application.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=startup_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        global STARTUP_MESSAGE_ID
        STARTUP_MESSAGE_ID = msg.message_id

    # Build Application with post_init hook
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).request(request).post_init(post_init).build()

    # Initialize components
    idle_monitor = IdleMonitor(application, None, perform_shutdown)
    job_manager = JobManager(application, idle_monitor, models_ready_event)
    idle_monitor.job_manager = job_manager
    files_handler = FilesHandler(job_manager, UPLOAD_FOLDER)

    # Filter for approved chat only
    chat_filter = filters.Chat(chat_id=TELEGRAM_CHAT_ID)

    # Handlers
    application.add_handler(CommandHandler(["start", "status"], status_command, filters=chat_filter))
    application.add_handler(CommandHandler("queue", queue_command, filters=chat_filter))
    application.add_handler(CommandHandler("extend", extend_command, filters=chat_filter))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.ATTACHMENT & chat_filter, files_handler.handle_files))


    # Error Handler with timestamped transient tracking (no shutdown on single update)
    _transient_error_counts: dict[str, tuple[int, float]] = {}  # name -> (count, window_start)
    MAX_TRANSIENT_RETRIES = 2
    TRANSIENT_WINDOW_SECONDS = 300

    async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):

        error = context.error
        error_name = type(error).__name__
        print(f"❌ Exception while handling an update: {error_name}: {error}")

        # Fatal auth state: bot blocked/kicked/deactivated. Do not retry as transient.
        if error_name == "Forbidden":
            print("🔴 [ERROR_HANDLER] Forbidden (bot blocked or lacks rights). Notifying admin, no shutdown.")
            try:
                if update and isinstance(update, Update) and update.effective_message:
                    await update.effective_message.reply_text(
                        "❌ Bot lacks rights for this action (Forbidden). Check group perms.",
                        parse_mode=ParseMode.MARKDOWN,
                    )
            except Exception:
                pass
            return

        # Flood control: honor Telegram retry_after instead of immediate retry.
        if error_name == "RetryAfter":
            delay = 30
            try:
                ra = getattr(error, "retry_after", 30)
                delay = int(ra.total_seconds()) if hasattr(ra, "total_seconds") else int(ra)
            except Exception:
                delay = 30
            delay = max(1, min(delay + 1, 300))
            print(f"⚠️ [ERROR_HANDLER] RetryAfter — backing off {delay}s")
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                pass
            return

        # List of transient network/connection errors that should NOT trigger shutdown
        transient_errors = (
            # httpx errors
            'ReadError', 'WriteError', 'ConnectError', 'ConnectTimeout', 'ReadTimeout', 'WriteTimeout',
            'PoolTimeout', 'CloseError', 'ProxyError', 'ProtocolError', 'RemoteProtocolError',
            'LocalProtocolError', 'UnsupportedProtocol', 'DecodingError',
            # SSL errors
            'SSLError', 'SSLCertVerificationError',
            # Telegram-bot errors (Forbidden/RetryAfter handled above)
            'TimeoutException', 'NetworkError', 'TimedOut',
            # General connection
            'ConnectionError', 'ConnectionResetError', 'ConnectionRefusedError', 'BrokenPipeError',
            'OSError', 'IOError', 'socket.error', 'socket.timeout'
        )

        if error_name in transient_errors:
            now = time.time()
            count, window_start = _transient_error_counts.get(error_name, (0, now))
            if now - window_start > TRANSIENT_WINDOW_SECONDS:
                count, window_start = 0, now
            count += 1
            _transient_error_counts[error_name] = (count, window_start)

            if count <= MAX_TRANSIENT_RETRIES:
                print(f"⚠️ [ERROR_HANDLER] Transient error {error_name} ({count}/{MAX_TRANSIENT_RETRIES}) - will retry")
                return  # Don't shutdown, let telegram-bot retry
            else:
                print(f"🔴 [ERROR_HANDLER] Transient error {error_name} exceeded {MAX_TRANSIENT_RETRIES} retries - network may be unstable")
                _transient_error_counts[error_name] = (0, now)  # Reset counter
                return  # Still don't shutdown, but log critical warning

        # Reset transient window on non-transient error (do not shutdown on single update)
        _transient_error_counts.clear()

        # Notify user if possible (redacted, truncated, no paths)
        try:
            if update and isinstance(update, Update) and update.effective_message:
                safe_err = str(error)[:200].replace("`", "'")
                text = f"❌ *An error occurred:* `{safe_err}`"
                await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception as notify_err:
            print(f"⚠️ [ERROR_HANDLER] Could not send error notification: {notify_err}")

        # NOTE: No perform_shutdown() here. Per-update errors must not kill the bot.
        # Shutdown is reserved for init failures (see initialize_models_background).

    application.add_error_handler(global_error_handler)

    # ⚡ FAST INIT: Initialize bot connection FIRST (before background tasks)
    # await application.initialize() -> Managed by run_polling
    # log("INIT", f"Bot online ({get_runtime()})")

    # Run polling - bot starts receiving messages immediately
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Bot stopped by user.")
    except Exception as e:
        print(f"❌ Application crashed: {e}")
        # Attempt to notify via Telegram if possible
        if 'application' in globals() and application:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(send_telegram_notification(application, f"❌ *CRASH REPORT:*\nBot crashed with error: `{e}`"))
            except Exception:
                pass
    finally:
        # Safety net: if perform_shutdown wasn't called (e.g. KeyboardInterrupt),
        # still clean up the runtime. perform_shutdown handles the normal path.
        if IS_COLAB or IS_KAGGLE:
            print("🔌 Runtime cleanup (safety net)...", flush=True)
            runtime.unassign()
