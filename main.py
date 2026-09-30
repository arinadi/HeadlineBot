# 🚀 Run Transcription Bot (Telegram Version - Modular)
# ------------------------------------------------------------------------------
# SECTION 1: IMPORT & CONFIGURATION
# ------------------------------------------------------------------------------

import asyncio
import os
import sys
import time
import uuid

import nest_asyncio
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.helpers import escape_markdown
from telegram.request import HTTPXRequest
from werkzeug.utils import secure_filename

from headlinebot import config
from headlinebot.bot_classes import FilesHandler, IdleMonitor, Job, JobManager
from headlinebot.config import Config
from headlinebot.image_editor import edit_image
from headlinebot.model_manager import discover_models
from headlinebot.utils import (
    format_duration,
    format_transcription_native,
    get_runtime,
    log,
    md_code,
    retouch_transcript,
    set_model_chains,
    summarize_text,
    transcribe_with_gemini,
)

# --- Transcription Mode ---
MODE = os.getenv('TRANSCRIPTION_MODE', 'GEMINI')

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
ENABLE_GEMINI_FEATURES = Config.ENABLE_GEMINI_FEATURES

# Detect Runtime Environment (Kaggle > Colab > Local)
IS_COLAB = False
IS_KAGGLE = False

try:
    from kaggle_secrets import UserSecretsClient
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

# --- Filesystem Setup ---
UPLOAD_FOLDER = 'uploads'
TRANSCRIPT_FOLDER = 'transcripts'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TRANSCRIPT_FOLDER, exist_ok=True)

# ------------------------------------------------------------------------------
# SECTION 3: AI AND HARDWARE INITIALIZATION
# ------------------------------------------------------------------------------

# Initial hardware detection (proxy)
# start.py sets MODE='WHISPER' only if it detects a GPU via nvidia-smi
device = "cuda" if MODE == 'WHISPER' else "cpu"

# Global State
model = None
gemini_client = None
# Set by initialize_models_background once the transcription engine (Whisper or the
# Gemini client) exists; the worker waits on it so no job runs against a None client.
models_ready_event = asyncio.Event()


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

    # 1. Notify admin
    try:
        if application:
            await send_telegram_notification(application, f"🔌 *Shutdown*\nReason: `{md_code(reason)}`\nUptime: `{uptime_str}`")
            log("SHUTDOWN", "Notification sent")
    except Exception as e:
        log("ERROR", f"Final notification failed: {e}")

    # 2. Ask run_polling to return. PTB forbids awaiting application.stop() from
    # inside a handler/task it is running; stop_running() is the supported way.
    try:
        if application:
            application.stop_running()
            log("SHUTDOWN", "Polling stop requested")
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

async def init_gemini():
    """Create the Gemini client and discover model chains (no-op without an API key)."""
    global gemini_client
    if not GEMINI_API_KEY:
        return
    from google import genai  # lazy: pulls in a large SDK
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    set_model_chains(await discover_models(gemini_client))
    log("INIT", "Gemini ready")


async def initialize_models_background():
    """Loads Whisper (if in WHISPER mode) and initializes Gemini client."""
    global model, MODE, device
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
            # Hardcoded file list for CTranslate2 model (no HF API needed)
            _files = ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]
            log("INIT", f"Downloading {len(_files)} files for {WHISPER_MODEL} via raw HTTP...")
            _repo = "Systran/faster-whisper-large-v2" if WHISPER_MODEL == "large-v2" else f"Systran/faster-whisper-{WHISPER_MODEL}"
            _local_dir = os.path.expanduser(f"~/.cache/whisper_models/{WHISPER_MODEL}")
            os.makedirs(_local_dir, exist_ok=True)

            import requests as _req
            hf_token = os.getenv("HF_TOKEN", "")
            _headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
            start_ts = time.time()

            _max_retries = 3
            for _fname in sorted(_files):
                _dest = os.path.join(_local_dir, _fname)
                if os.path.exists(_dest):
                    continue
                _url = f"https://huggingface.co/{_repo}/resolve/main/{_fname}"
                _downloaded = False
                for _attempt in range(1, _max_retries + 1):
                    try:
                        log("INIT", f"  Downloading: {_fname}" + (f" (attempt {_attempt}/{_max_retries})" if _attempt > 1 else ""))
                        _resp = await asyncio.to_thread(_req.get, _url, headers=_headers, stream=True, timeout=(10, 300))
                        _resp.raise_for_status()
                        _total = int(_resp.headers.get("content-length", 0))
                        _downloaded_bytes = 0
                        with open(_dest + ".part", "wb") as _f:
                            for _chunk in _resp.iter_content(chunk_size=8*1024*1024):
                                _f.write(_chunk)
                                _downloaded_bytes += len(_chunk)
                                if _total:
                                    _pct = _downloaded_bytes * 100 // _total
                                    if _pct % 20 == 0:
                                        log("INIT", f"    {_fname}: {_pct}%")
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
                            os.remove(_part)
                        if _attempt < _max_retries:
                            _delay = 2 ** _attempt
                            log("INIT", f"  Retrying in {_delay}s...")
                            await asyncio.sleep(_delay)
                if not _downloaded:
                    raise RuntimeError(f"Failed to download {_fname} after {_max_retries} attempts")

            elapsed = time.time() - start_ts
            log("INIT", f"All {len(_files)} files downloaded in {elapsed:.0f}s")

            model = await asyncio.to_thread(
                WhisperModel,
                _local_dir,
                device=device,
                compute_type=compute_type
            )
            log("INIT", f"Whisper loaded ({compute_type})")

        if SHUTDOWN_IN_PROGRESS: return

        await init_gemini()

        if SHUTDOWN_IN_PROGRESS: return

        models_ready_event.set()

        # Update startup message
        await update_startup_message()
        await send_telegram_notification(application, "🛎️ *Kitchen is now open!* All AI systems are ready to process your orders.")

    except Exception as e:
        if SHUTDOWN_IN_PROGRESS: return
        log("ERROR", f"Initialization failed: {e}")
        if MODE == 'WHISPER':
            log("INIT", "Whisper unavailable, falling back to Gemini Cloud...")
            await send_telegram_notification(application, f"⚠️ *Whisper unavailable.* Falling back to Gemini Cloud.\nError: `{md_code(str(e)[:150])}`")
            MODE = 'GEMINI'
            os.environ['TRANSCRIPTION_MODE'] = 'GEMINI'
            device = "cpu"
            try:
                await init_gemini()
                models_ready_event.set()
                await update_startup_message()
                await send_telegram_notification(application, "🛎️ *Kitchen is now open!* Running on Gemini Cloud.")
                return
            except Exception as e2:
                log("ERROR", f"Gemini fallback also failed: {e2}")
                await send_telegram_notification(application, f"❌ *FATAL:* Both Whisper & Gemini failed:\n`{md_code(str(e2))}`")
        await perform_shutdown("AI Model Loading Failed")


def startup_message() -> tuple[str, InlineKeyboardMarkup]:
    """Text and keyboard of the pinned-style startup message, for its current state."""
    ai_status = "✅ Kitchen Open" if models_ready_event.is_set() else "⏳ Preparing..."
    hardware_label = "NVIDIA GPU" if device == "cuda" else "Standard CPU"
    text = (
        f"📰 *Welcome to HeadlineBot*\n"
        f"Your AI assistant for front-line reporting. Send your files anytime.\n\n"
        f"🛠️ *Equipment:* `{hardware_label}`\n"
        f"🤖 *AI Engine:* `{'Gemini Cloud' if MODE == 'GEMINI' else WHISPER_MODEL}`\n"
        f"📢 *Status:* {ai_status}\n"
        f"📂 *Order Limit:* `{BOT_FILESIZE_LIMIT}MB` per file"
    )
    keyboard = [[InlineKeyboardButton("🔌 Close Restaurant", callback_data="shutdown_bot")]]
    return text, InlineKeyboardMarkup(keyboard)


async def update_startup_message():
    """Updates the persistent startup message with current status."""
    if not STARTUP_MESSAGE_ID:
        return
    text, keyboard = startup_message()
    try:
        await application.bot.edit_message_text(
            chat_id=TELEGRAM_CHAT_ID,
            message_id=STARTUP_MESSAGE_ID,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
    except Exception as e:
        log("ERROR", f"Failed to update startup message: {e}")


def run_transcription_process(job: Job) -> tuple[str, str]:
    """Runs the blocking Whisper transcription in a separate thread."""
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
    formatted_text = format_transcription_native(segments)

    log("WHISPER", f"[{job.job_id}] Done: {len(segments)} segments, lang={info.language} ({info.language_probability:.0%})")

    return formatted_text, info.language if info.language else 'N/A'

async def _process_image_job(job: Job, _start_time: float):
    """Process an image color correction job."""
    await application.bot.send_message(job.chat_id, f"🎨 Analyzing `{md_code(job.original_filename)}`...", parse_mode=ParseMode.MARKDOWN, reply_to_message_id=job.message_id)

    # Generate output path
    base_name = os.path.splitext(job.original_filename)[0]
    ext = os.path.splitext(job.original_filename)[1].lower()
    if ext not in ('.jpg', '.jpeg'):
        ext = '.jpg'
    output_filename = f"edited_{base_name}{ext}"
    output_path = os.path.join(IMAGE_OUTPUT_FOLDER, f"{uuid.uuid4().hex}_{output_filename}")

    # Process
    if gemini_client and ENABLE_GEMINI_FEATURES:
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
                await job._original_message.reply_photo(photo=img_file, caption="⚠️ AI correction failed. Original sent.")
            log("ERROR", f"[{job.job_id}] Image edit failed: {result.get('error')}")
    else:
        # AI features off (ENABLE_GEMINI_FEATURES) or no Gemini client — send original
        with open(job.local_filepath, 'rb') as img_file:
            await job._original_message.reply_photo(photo=img_file, caption="⚠️ AI color correction is off. Original sent.")

    # Cleanup output file
    if os.path.exists(output_path):
        os.remove(output_path)


async def _process_transcript_job(job: Job, start_time: float):
    """Process a transcription job (transcript + summary + retouch)."""
    duration_str = format_duration(job.audio_duration)
    await application.bot.send_message(job.chat_id, f"▶️ Processing `{md_code(job.original_filename)}` ({duration_str})...", parse_mode=ParseMode.MARKDOWN, reply_to_message_id=job.message_id)

    # 1. Transcribe
    if MODE == 'GEMINI':
        transcript_text, detected_language = await transcribe_with_gemini(job.local_filepath, gemini_client)
    else:
        transcript_text, detected_language = await asyncio.to_thread(run_transcription_process, job)

    if job.status == 'cancelled':
        raise asyncio.CancelledError("Job cancelled during transcription.")

    base_name = os.path.splitext(job.original_filename)[0]
    safe_name = secure_filename(base_name)[:50]
    ts_filename = f"{TRANSCRIPT_FILENAME_PREFIX}_({duration_str.replace(' ', '')})_{safe_name}.txt"
    ts_filepath = os.path.join(TRANSCRIPT_FOLDER, ts_filename)
    with open(ts_filepath, "w", encoding="utf-8") as f:
        f.write(transcript_text)

    # Send transcript
    processing_duration_str = format_duration(time.time() - start_time)
    log("JOB", f"[{job.job_id}] Transcription done in {processing_duration_str}")

    result_text = (f"✅ *Done!* `{md_code(job.original_filename)}`\n"
                   f"⏱️ {duration_str} audio → {processing_duration_str} process\n"
                   f"🌐 Lang: {detected_language.upper()}\n"
                   f"🤖 Generating AI Summary...")
    await application.bot.send_message(job.chat_id, result_text, parse_mode=ParseMode.MARKDOWN, reply_to_message_id=job.message_id)

    with open(ts_filepath, 'rb') as ts_file:
        await application.bot.send_document(job.chat_id, document=ts_file, filename=ts_filename, reply_to_message_id=job.message_id)

    # 2. AI Summary + Retouch — PARALLEL, send 1-by-1 as each succeeds
    if gemini_client and ENABLE_GEMINI_FEATURES:
        async def _generate_and_send(kind: str, prefix: str, generate):
            log("JOB", f"[{job.job_id}] Generating {kind}...")
            text = await generate(transcript_text, gemini_client)
            if not text:
                return
            filename = f"{prefix}_({duration_str.replace(' ', '')})_{safe_name}.txt"
            filepath = os.path.join(TRANSCRIPT_FOLDER, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            with open(filepath, 'rb') as doc:
                await application.bot.send_document(job.chat_id, document=doc, filename=filename, reply_to_message_id=job.message_id)
            log("JOB", f"[{job.job_id}] {kind.capitalize()} sent.")

        tasks = [_generate_and_send("summary", SUMMARY_FILENAME_PREFIX, summarize_text)]
        # Retouch only for Whisper output; Gemini transcripts are already formatted by the prompt.
        if MODE == 'WHISPER':
            tasks.append(_generate_and_send("retouch", RETOUCH_FILENAME_PREFIX, retouch_transcript))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                log("ERROR", f"AI task failed: {r}")
                await application.bot.send_message(job.chat_id, f"⚠️ AI Failed: {r}", reply_to_message_id=job.message_id)


async def queue_processor():
    """The main worker loop that processes jobs from the queue one by one."""
    log("WORKER", "Waiting for AI models...")
    await models_ready_event.wait()
    log("WORKER", "Models ready. Processing jobs...")
    last_heartbeat = time.time()
    while not SHUTDOWN_IN_PROGRESS:
        # Heartbeat every 60s — keeps Kaggle alive (prevents idle kill)
        if time.time() - last_heartbeat >= 60:
            qsize = job_manager.job_queue.qsize()
            processing = job_manager.currently_processing
            status = f"processing {processing.original_filename}" if processing else "idle"
            log("HEARTBEAT", f"Queue={qsize} | Status={status}")
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
                await application.bot.send_message(job.chat_id, f"❌ *Failed:* `{md_code(job.original_filename)}`\n`{md_code(e)}`", parse_mode=ParseMode.MARKDOWN, reply_to_message_id=job.message_id)
            except Exception:
                log("ERROR", f"[{job.job_id}] Failed to send error notification")
        finally:
            if os.path.exists(job.local_filepath):
                try:
                    os.remove(job.local_filepath)
                except Exception:
                    pass

            job_manager.job_queue.task_done()
            job_manager.complete_job(job.job_id)

# ------------------------------------------------------------------------------
# SECTION 6: TELEGRAM UI COMMANDS
# ------------------------------------------------------------------------------

async def get_status_text_and_keyboard():
    """Builds the dynamic status message text and keyboard."""
    processing_job = job_manager.currently_processing
    if processing_job:
        processing_line = f"👨‍🍳 *Currently Cooking:* `{md_code(processing_job.original_filename)}`\n"
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
        lines.append(f"\n▶️ *Currently Processing*\n`{md_code(processing_job.original_filename)}`\n(By: {escape_markdown(processing_job.author_display_name)})")
    if queued_jobs:
        queue_text = [f"*{i}.* `{md_code(job.original_filename)}` (By: {escape_markdown(job.author_display_name)})" for i, job in enumerate(queued_jobs, 1)]
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
    # CallbackQueryHandler has no chat filter, and a forwarded bot message keeps its
    # buttons — without this check anyone could press shutdown/cancel from another chat.
    if not query.message or query.message.chat_id != TELEGRAM_CHAT_ID:
        await query.answer("⛔ Not allowed here.", show_alert=True)
        log("SECURITY", f"Blocked callback '{query.data}' from user {query.from_user.id if query.from_user else '?'}")
        return
    await query.answer()
    data = query.data

    if data == "refresh_status":
        text, reply_markup = await get_status_text_and_keyboard()
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        except telegram.error.BadRequest:
            pass
    elif data == "shutdown_bot":
        # Two-step: one mis-tap on 🔌 would otherwise kill the runtime and every queued job.
        keyboard = [[InlineKeyboardButton("✅ Yes, shut down", callback_data="shutdown_confirm"),
                     InlineKeyboardButton("« Cancel", callback_data="refresh_status")]]
        await query.edit_message_text("🔌 *Shut down the bot?*\nQueued jobs will be lost.",
                                      reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    elif data == "shutdown_confirm":
        await query.edit_message_text("🔴 *MANUAL SHUTDOWN INITIATED...*", parse_mode=ParseMode.MARKDOWN)
        await perform_shutdown(f"Manual Shutdown by {query.from_user.first_name}")
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
        msg = f"✅ Job `{md_code(job_name)}` was cancelled." if cancelled else "❌ Could not cancel job."
        await query.edit_message_text(msg, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
    elif data == "extend_idle":
        # Rate limit check (5 minutes = 300 seconds)
        if time.time() - idle_monitor.last_extend_time < 300:
            await query.answer("⏳ Please wait 5 minutes before extending again.", show_alert=True)
            return

        if idle_monitor.extend_timer(5):
            idle_monitor.last_extend_time = time.time()
            new_text = f"✅ *Idle Extended*\nTimer added +5 minutes.\n_Action by {escape_markdown(query.from_user.first_name)}_"
            await query.edit_message_text(new_text, parse_mode=ParseMode.MARKDOWN)
        else:
            await query.edit_message_text("ℹ️ Bot is already active, no need to extend.", parse_mode=ParseMode.MARKDOWN)

# ------------------------------------------------------------------------------
# SECTION 7: MAIN ENTRY POINT
# ------------------------------------------------------------------------------

def main():
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

        if ENABLE_IDLE_MONITOR:
            idle_monitor.start()

        text, keyboard = startup_message()
        msg = await application.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        global STARTUP_MESSAGE_ID
        STARTUP_MESSAGE_ID = msg.message_id

    # Build Application with post_init hook
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).request(request).post_init(post_init).build()

    # Initialize components
    # CPU/GEMINI runtimes are cheap to keep and users there upload slowly, so idle
    # timers run 5x longer than on a paid GPU.
    idle_monitor = IdleMonitor(application, None, perform_shutdown,
                               timeout_multiplier=5 if MODE == 'GEMINI' else 1)
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


    async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        """Logs handler errors and tells the user. Never shuts down: one bad update
        (e.g. a Markdown BadRequest from an odd filename) must not kill the bot."""
        error = context.error
        # PTB already retries network failures and flood waits (RetryAfter) itself.
        if isinstance(error, (telegram.error.NetworkError, telegram.error.RetryAfter)):
            log("ERROR", f"Transient Telegram error: {type(error).__name__}: {error}")
            return
        # Bot blocked/kicked from that chat: replying there would fail the same way.
        if isinstance(error, telegram.error.Forbidden):
            log("ERROR", f"Forbidden: {error}")
            return

        log("ERROR", f"Unhandled error in update handler: {type(error).__name__}: {error}")
        try:
            if isinstance(update, Update) and update.effective_message:
                # Plain text: the error message itself may contain Markdown characters.
                await update.effective_message.reply_text(f"❌ An error occurred: {error}")
        except Exception as notify_err:
            log("ERROR", f"Could not send error notification: {notify_err}")

    application.add_error_handler(global_error_handler)

    # run_polling is synchronous (it owns the event loop); awaiting its None return
    # used to raise TypeError, so every clean shutdown was reported as a crash.
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("🛑 Bot stopped by user.")
    except Exception as e:
        print(f"❌ Application crashed: {e}")
        # Attempt to notify via Telegram if possible
        if 'application' in globals() and application:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(send_telegram_notification(application, f"❌ *CRASH REPORT:*\nBot crashed with error: `{md_code(e)}`"))
            except Exception:
                pass
    finally:
        # Safety net: if perform_shutdown wasn't called (e.g. KeyboardInterrupt),
        # still clean up the runtime. perform_shutdown handles the normal path.
        if IS_COLAB or IS_KAGGLE:
            print("🔌 Runtime cleanup (safety net)...", flush=True)
            runtime.unassign()
