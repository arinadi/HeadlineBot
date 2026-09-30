import asyncio
import os
import time
from datetime import datetime

from headlinebot import config

# --- Logging Utilities (Merged from log_utils.py) ---

def get_runtime() -> str:
    """Formats total runtime since INIT_START as 'Xm XXs'."""
    elapsed = time.time() - config.INIT_START
    minutes, seconds = divmod(int(elapsed), 60)
    return f"{minutes}m {seconds:02d}s"

def log(category: str, message: str):
    """
    Print log with format: [HH:MM:SS] [+Runtime] [CATEGORY] message

    Categories: INIT, JOB, IDLE, WORKER, GEMINI, WHISPER, FILE, ERROR
    """
    timestamp = time.strftime("%H:%M:%S")
    runtime = get_runtime()
    print(f"[{timestamp}] [+{runtime}] [{category}] {message}")

def md_code(text: str) -> str:
    """Make user text safe inside a Markdown `code span`.

    Telegram's legacy Markdown has no escape inside code spans, so a stray backtick
    (e.g. in a filename) ends the span early and the whole message is rejected.
    """
    return str(text).replace("`", "'")

# --- AI & Formatting Utilities ---

# Model chains are discovered at startup via model_manager.py
# Fallback defaults if discovery fails
GEMMA_MODEL = config.GEMMA_MODEL
GEMINI_PRIMARY = "gemini-3-flash-preview"
GEMINI_FALLBACK = "gemini-2.5-flash"

# Global model chains (set at startup)
_model_chains = None


def set_model_chains(chains: dict):
    """Set model chains from model_manager.discover_models()."""
    global _model_chains
    _model_chains = chains


def get_model_chain(task: str) -> dict:
    """Get model chain for a specific task."""
    if _model_chains and task in _model_chains:
        return _model_chains[task]
    # Fallback defaults
    return {
        "primary": GEMMA_MODEL if task in ("summary", "retouch") else GEMINI_PRIMARY,
        "fallbacks": [GEMINI_PRIMARY, GEMINI_FALLBACK],
        "all": [GEMMA_MODEL, GEMINI_PRIMARY, GEMINI_FALLBACK] if task in ("summary", "retouch") else [GEMINI_PRIMARY, GEMINI_FALLBACK],
    }

def build_journalist_summary_prompt(today_date: str, file_metadata: str | None = None) -> str:
    """Builder for the summarization prompt."""
    prompt = (
        "Anda adalah AI peringkas untuk jurnalis. "
        "Ringkas transkrip berikut ke dalam Bahasa Indonesia dengan format Plain Text.\n\n"
    )

    if file_metadata:
        prompt += (
            "INFORMASI METADATA FILE AUDIO (Sebagai Konteks Tambahan):\n"
            f"{file_metadata}\n\n"
        )

    prompt += (
        "ATURAN PENTING:\n"
        "- JANGAN mengarang atau berasumsi informasi yang tidak ada di transkrip.\n"
        "- Jika informasi tidak ditemukan, KOSONGKAN bagian tersebut atau tulis '-'.\n"
        "- Hanya tulis informasi yang JELAS terlihat di transkrip.\n"
        f"- Jika tanggal tidak disebutkan di transkrip, gunakan: {today_date}\n\n"
        "FORMAT OUTPUT:\n\n"
        "FAKTA BERITA\n"
        f"Tanggal: [tanggal dari transkrip atau {today_date}]\n\n"
        "LEAD (Paragraf Pembuka):\n"
        "[1-2 kalimat inti berita: siapa, apa, kapan, dimana]\n\n"
        "BODY:\n"
        "A. [Topik/Angle 1]\n"
        "   - Detail penting\n"
        "   - Kutipan pendukung (jika ada)\n\n"
        "B. [Topik/Angle 2]\n"
        "   - Detail penting\n\n"
        "C. [Topik/Angle 3, jika ada]\n"
        "   - Detail penting\n\n"
        "D. [Topik/Angle 4, jika ada]\n"
        "   - Detail penting\n\n"
        "NARASUMBER:\n"
        "1. [Nama] - [Jabatan] - \"[Kutipan kunci]\"\n"
        "(Kosongkan jika tidak ada narasumber jelas)\n\n"
        "DATA PENDUKUNG:\n"
        "- [Angka/statistik dari transkrip]\n"
        "(Kosongkan jika tidak ada data)\n\n"
        "PERLU KLARIFIKASI:\n"
        "- [Hal yang tidak jelas atau perlu dicek]\n"
        "(Kosongkan jika tidak ada)\n\n"
        "-----\n"
    )
    return prompt


def build_retouch_prompt() -> str:
    """Builder for the retouch/transcript cleanup prompt."""
    return (
        "Anda adalah editor transkrip untuk jurnalis. "
        "Perbaiki transkrip berikut agar lebih mudah dibaca.\n\n"
        "ATURAN:\n"
        "- Perbaiki typo, kesalahan penulisan, serta tanda baca (tanda tanya, koma, dll).\n"
        "- Berikan jeda baris (enter) di setiap akhir paragraf agar teks lebih mudah dibaca.\n"
        "- Pastikan urutan kalimat dan struktur asli teks tetap sama.\n"
        "- JANGAN mengubah isi, makna, atau menambah informasi baru.\n"
        "- JANGAN mengarang atau berasumsi.\n"
        "- Output hanya transkrip yang sudah diperbaiki, tanpa penjelasan tambahan.\n\n"
        "-----\n"
    )


async def summarize_text(transcript: str, llm, session: str | None = None) -> str:
    """Generates a journalist-friendly summary of the transcript with the AI provider
    (headlinebot/llm.py). Raises on failure, so an error message is never saved as the summary.
    """
    today_date = datetime.now().strftime("%d %B %Y")
    prompt = build_journalist_summary_prompt(today_date)
    return await llm.generate(task="summary", system=prompt, text=transcript, temperature=0.3, session=session)


async def retouch_transcript(transcript: str, llm, session: str | None = None) -> str:
    """Retouch/clean up transcript: fix typos, punctuation, add paragraph breaks.
    Returns the original transcript if every model fails (a retouch is optional polish).
    """
    try:
        return await llm.generate(task="retouch", system=build_retouch_prompt(), text=transcript,
                                  temperature=0.3, session=session)
    except RuntimeError as e:
        log("ERROR", f"Retouch failed, keeping original transcript: {e}")
        return transcript


def format_duration(seconds: float) -> str:
    """Converts a duration in seconds to a human-readable 'Xm XXs' format."""
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "N/A"
    minutes, remaining_seconds = divmod(int(seconds), 60)
    return f"{minutes}m {remaining_seconds:02d}s"


def get_val(seg, key, default=0.0):
    """Helper to safely access attributes (handles dict vs object)."""
    if hasattr(seg, key):
        return getattr(seg, key)
    elif isinstance(seg, dict):
        return seg.get(key, default)
    return default

def format_transcription_native(segments: list) -> str:
    """
    Formats Whisper segments exactly as output by the model (with VAD enabled).
    Format: [HH:MM:SS] Text
    """
    if not segments:
        return ""

    lines = []
    for seg in segments:
        text = str(get_val(seg, 'text', '')).strip()
        if not text:
            continue

        lines.append(f"{text}")

    return "\n\n".join(lines)

async def transcribe_with_gemini(local_filepath: str, gemini_client) -> tuple[str, str]:
    """Transcribes audio using Gemini API (File API).
    Uses model chain: primary (flash) → fallbacks.
    Raises on failure, so an error message is never saved as the transcript.
    The uploaded audio is always deleted from Gemini afterwards (privacy, storage quota).
    """
    if not gemini_client:
        raise RuntimeError("Gemini client not initialized")

    audio_file = None
    try:
        log("GEMINI", f"Uploading {os.path.basename(local_filepath)}...")
        # 1. Upload (max 60s)
        audio_file = await asyncio.wait_for(
            asyncio.to_thread(gemini_client.files.upload, file=local_filepath),
            timeout=60
        )

        # 2. Wait for ACTIVE (max 5 minutes)
        log("GEMINI", "Waiting for file processing...")
        max_polls = 150  # 150 * 2s = 300s = 5 minutes
        for _ in range(max_polls):
            audio_file = await asyncio.wait_for(
                asyncio.to_thread(gemini_client.files.get, name=audio_file.name),
                timeout=30
            )
            if audio_file.state.name == "ACTIVE":
                break
            elif audio_file.state.name != "PROCESSING":
                raise Exception(f"File failed to process. State: {audio_file.state.name}")
            await asyncio.sleep(2)
        else:
            raise Exception("Gemini file processing timed out after 5 minutes")

        # 3. Generate Transcript using model chain
        prompt = (
            "Transcribe this audio file accurately. Identify different speakers if possible. "
            "Output only the transcript.\n"
            "STRICT FORMATTING RULE:\n"
            "- DO NOT include timestamps.\n"
            "- Insert a double newline (\\n\\n) after every sentence/period.\n"
            "- Do not change any words, order, or content.\n"
            "- Simply ensure there is a blank line between every sentence for readability."
        )

        from headlinebot.model_manager import try_model_chain
        chain = get_model_chain("transcript")

        response = await try_model_chain(
            gemini_client, chain, [audio_file, prompt],
            task_name="transcript"
        )

        if response and response.text:
            return response.text, "ID"
        raise RuntimeError("All models failed for transcription")

    finally:
        if audio_file is not None:
            try:
                await asyncio.to_thread(gemini_client.files.delete, name=audio_file.name)
            except Exception as e:
                # Cleanup only: the transcription result (or its error) matters more.
                log("ERROR", f"Could not delete {audio_file.name} from Gemini: {e}")
