from datetime import datetime
import asyncio
import time
import os
import config

# --- Logging Utilities (Merged from log_utils.py) ---

def get_runtime() -> str:
    """Formats total runtime since INIT_START as 'Xm XXs'."""
    elapsed = time.time() - config.INIT_START
    minutes, seconds = divmod(int(elapsed), 60)
    return f"{minutes}m {seconds:02d}s"

def log(category: str, message: str):
    """
    Print log with format: [HH:MM:SS] [+Runtime] [CATEGORY] message

    Categories: INIT, JOB, IDLE, WORKER, GEMINI, WHISPER, FILE, GRADIO, ERROR
    """
    timestamp = time.strftime("%H:%M:%S")
    runtime = get_runtime()
    print(f"[{timestamp}] [+{runtime}] [{category}] {message}")

# --- AI & Formatting Utilities ---

# Model hierarchy:
# - Summary/Retouch: Gemma 4 (no fallback)
# - Transcript CPU: Gemini 3.5 Flash (primary) → Gemini 2.5 Flash (fallback)
GEMMA_MODEL = "models/gemma-4-26b-a4b-it"
GEMINI_PRIMARY = "gemini-3-flash-preview"
GEMINI_FALLBACK = "gemini-2.5-flash"

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


async def summarize_text(transcript: str, gemini_client) -> str:
    """Generates a journalist-friendly summary of the transcript.
    Primary: Gemma 4 (no fallback).
    """
    if not gemini_client:
        return "Summarization disabled: Gemini API key not configured or client failed to load."

    today_date = datetime.now().strftime("%d %B %Y")
    prompt = build_journalist_summary_prompt(today_date)

    from google.genai import types

    try:
        log("GEMMA", f"Requesting summary ({len(transcript)} chars) with {GEMMA_MODEL}...")
        response = await asyncio.to_thread(
            gemini_client.models.generate_content,
            model=GEMMA_MODEL,
            contents=[prompt, transcript],
            config=types.GenerateContentConfig(temperature=0.3),
        )
        log("GEMMA", f"Summary received ({len(response.text)} chars)")
        return response.text
    except Exception as e:
        log("ERROR", f"Gemma summary failed: {e}")
        return f"❌ Error generating summary: {e}"


async def retouch_transcript(transcript: str, gemini_client) -> str:
    """Retouch/clean up transcript: fix typos, punctuation, add paragraph breaks.
    Primary: Gemma 4 (no fallback).
    """
    if not gemini_client:
        return transcript  # Return original if no client

    prompt = build_retouch_prompt()
    contents = [prompt, transcript]

    from google.genai import types

    try:
        log("GEMMA", f"Requesting retouch ({len(transcript)} chars) with {GEMMA_MODEL}...")
        response = await asyncio.to_thread(
            gemini_client.models.generate_content,
            model=GEMMA_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(temperature=0.3),
        )
        log("GEMMA", f"Retouch received ({len(response.text)} chars)")
        return response.text
    except Exception as e:
        log("ERROR", f"Gemma retouch failed: {e}")
        return transcript  # Return original on error


def format_duration(seconds: float) -> str:
    """Converts a duration in seconds to a human-readable 'Xm XXs' format."""
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "N/A"
    minutes, remaining_seconds = divmod(int(seconds), 60)
    return f"{minutes}m {remaining_seconds:02d}s"

def format_timestamp(seconds: float) -> str:
    """Formats seconds into [HH:MM:SS] or [MM:SS]."""
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "[00:00]"

    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    return f"{minutes:02d}:{secs:02d}"

def get_val(seg, key, default=0.0):
    """Helper to safely access attributes (handles dict vs object)."""
    if hasattr(seg, key):
        return getattr(seg, key)
    elif isinstance(seg, dict):
        return seg.get(key, default)
    return default

def format_transcription_with_pauses(segments: list, pause_thresh: float = 2.0) -> str:
    """
    Formats Whisper segments with timestamps at significant pauses.
    """
    if not segments:
        return ""

    # 1. Normalize and clean segments
    clean_segments = []
    for seg in segments:
        text = str(get_val(seg, 'text', '')).strip()
        if not text:
            continue

        start = float(get_val(seg, 'start', 0.0))
        end = float(get_val(seg, 'end', start))

        clean_segments.append({
            'start': start,
            'end': end,
            'text': text
        })

    if not clean_segments:
        return ""

    # 2. Build blocks based on pauses
    blocks: list[str] = []
    current_block_start = float(clean_segments[0]['start'])
    current_text_parts = [str(clean_segments[0]['text'])]
    last_end = clean_segments[0]['end']

    for i in range(1, len(clean_segments)):
        seg = clean_segments[i]
        gap = float(seg['start']) - float(last_end)

        if gap > pause_thresh:
            # Commit previous block
            timestamp = format_timestamp(float(current_block_start))
            block_content = " ".join(str(p) for p in current_text_parts)
            blocks.append(f"{timestamp}\n{block_content}")

            # Start new block
            current_block_start = seg['start']
            current_text_parts = [seg['text']]
        else:
            # Continue current block
            current_text_parts.append(seg['text'])

        last_end = seg['end']

    # 3. Commit final block
    if current_text_parts:
        timestamp = format_timestamp(float(current_block_start))
        block_content = " ".join(str(p) for p in current_text_parts)
        blocks.append(f"{timestamp}\n{block_content}")

    return "\n\n".join(blocks)

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

async def transcribe_with_gemini(local_filepath: str, duration: float, gemini_client) -> tuple[str, str]:
    """Transcribes audio using Gemini API (File API).
    Primary: Gemini 3.5 Flash. Fallback: Gemini 2.5 Flash.
    """
    if not gemini_client:
        return "Error: Gemini client not initialized.", "N/A"

    try:
        log("GEMINI", f"Uploading {os.path.basename(local_filepath)}...")
        # 1. Upload
        audio_file = await asyncio.to_thread(
            gemini_client.files.upload,
            file=local_filepath
        )

        # 2. Wait for ACTIVE
        log("GEMINI", "Waiting for file processing...")
        while True:
            audio_file = await asyncio.to_thread(
                gemini_client.files.get,
                name=audio_file.name
            )
            if audio_file.state.name == "ACTIVE":
                break
            elif audio_file.state.name != "PROCESSING":
                raise Exception(f"File failed to process. State: {audio_file.state.name}")
            await asyncio.sleep(2)

        # 3. Generate Transcript
        prompt = (
            "Transcribe this audio file accurately. Identify different speakers if possible. "
            "Output only the transcript.\n"
            "STRICT FORMATTING RULE:\n"
            "- DO NOT include timestamps.\n"
            "- Insert a double newline (\\n\\n) after every sentence/period.\n"
            "- Do not change any words, order, or content.\n"
            "- Simply ensure there is a blank line between every sentence for readability."
        )

        # Try Gemini 3.5 Flash first, fallback to 2.5 Flash
        for model_name in [GEMINI_PRIMARY, GEMINI_FALLBACK]:
            try:
                log("GEMINI", f"Generating transcript with {model_name} for {duration:.1f}s audio...")
                response = await asyncio.to_thread(
                    gemini_client.models.generate_content,
                    model=model_name,
                    contents=[audio_file, prompt]
                )
                if response.text:
                    log("GEMINI", f"Transcript received with {model_name}")
                    return response.text, "ID"
            except Exception as model_error:
                log("GEMINI", f"{model_name} failed: {model_error}, trying next...")
                continue

        # All models failed
        return "Error: All Gemini models failed for transcription.", "N/A"

    except Exception as e:
        log("ERROR", f"Gemini transcription failed: {e}")
        return f"Error transcribing with Gemini: {e}", "N/A"
