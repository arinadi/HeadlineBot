"""HeadlineBot settings.

Secrets come from the environment (loaded from .env by the launch scripts).
Everything else is a plain constant: change it here and push; Colab and the
VPS launcher always run the latest code of their branch.
"""
import os
import time

# Start of this run, set by runner.py so logged uptimes include setup time.
INIT_START = float(os.getenv('INIT_START', time.time()))

# prod or beta, set by runner.py / colab-run.sh --version.
HEADLINEBOT_VERSION = os.getenv('HEADLINEBOT_VERSION', 'prod')

# --- Secrets (from .env) ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')    # from @BotFather
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')        # the only chat the bot serves
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')            # CPU transcription; LLM_PROVIDER "gemini"
OPENAI_COMPAT_API_KEY = os.environ.get('OPENAI_COMPAT_API_KEY')  # LLM_PROVIDER "openai_compat"
HF_TOKEN = os.environ.get('HF_TOKEN')                        # optional: faster Whisper model download

if TELEGRAM_CHAT_ID:
    TELEGRAM_CHAT_ID = int(TELEGRAM_CHAT_ID)

# --- Whisper (GPU transcription) ---
# Model size: tiny, base, small, medium, large-v2, large-v3. Larger = slower but more accurate.
WHISPER_MODEL = 'large-v2'
# compute_type: 'auto' (float16 on CUDA, int8 on CPU), 'float16', 'int8', 'float32'.
WHISPER_PRECISION = 'auto'
# Beam size: paths searched. Higher (5-10) = better accuracy, slower.
WHISPER_BEAM_SIZE = 10
# Patience: higher (2.0+) forces a deeper beam search. Requires temperature 0.
WHISPER_PATIENCE = 2.0
# Temperature: 0 = deterministic (best for long recordings).
WHISPER_TEMPERATURE = 0.0
# Repetition penalty > 1.0 reduces loops.
WHISPER_REPETITION_PENALTY = 1.1
# Never repeat the same N-word sequence.
WHISPER_NO_REPEAT_NGRAM_SIZE = 3

# --- VAD (voice activity detection) ---
VAD_FILTER = False                  # drop silence to reduce hallucinations
VAD_THRESHOLD = 0.5                 # speech probability (0.1-1.0); higher = stricter
VAD_MIN_SPEECH_DURATION_MS = 250    # shorter sounds are ignored
VAD_MIN_SILENCE_DURATION_MS = 2000  # silence that starts a new segment
VAD_SPEECH_PAD_MS = 400             # padding so words aren't cut

# --- Limits ---
BOT_FILESIZE_LIMIT = 20  # MB per file (Telegram bots can't download more)

# --- Idle monitor: release the Colab runtime when nobody uses the bot ---
ENABLE_IDLE_MONITOR = True
IDLE_FIRST_ALERT_MINUTES = 1
IDLE_FINAL_WARNING_MINUTES = 5
# Beta runs are test runs: give quota back sooner.
IDLE_SHUTDOWN_MINUTES = 5 if HEADLINEBOT_VERSION == 'beta' else 10

# --- AI features: summary, retouch, photo correction ---
ENABLE_AI_FEATURES = True
# 'openai_compat' (any OpenAI-compatible API, e.g. OpenCode Go) or 'gemini'.
# Transcription is separate: Whisper on GPU, Gemini on CPU. See headlinebot/llm.py.
LLM_PROVIDER = 'openai_compat'
OPENAI_COMPAT_BASE_URL = 'https://opencode.ai/zen/go/v1'
# Tried in order. Vision models must accept image input (photo correction);
# these were checked against OpenCode Go on 2026-09-30.
OPENAI_COMPAT_MODELS = ['deepseek-v4.1-flash', 'kimi-k3']
OPENAI_COMPAT_VISION_MODELS = ['deepseek-v4.1-flash', 'glm-5.3-flash']

# --- Photo correction ---
GEMMA_MODEL = 'models/gemma-4-26b-a4b-it'  # image model when LLM_PROVIDER is 'gemini'
JPEG_QUALITY = 95                          # output quality (1-100)
