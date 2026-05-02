# 🤖 TTB (Telegram Transcription Bot)

**TTB** is an advanced Telegram bot that utilizes **OpenAI Whisper** for high-precision audio/video transcription and **Google Gemini** for automatic summarization in Indonesian (default).

Specifically designed to run on **Google Colab** (Free GPU) using the "Vibe Coding" method, where this repository acts as the *source of truth* pulled by Colab at *runtime*.

## ⚡ Limits & Compatibility

| Component | Type | Limit |
| :--- | :--- | :--- |
| **Whisper (Transcription)** | **Fully Local** (Colab GPU) | **Unlimited**. No duration or file count limits. Runs 100% offline once model is loaded. |
| **Hugging Face** | Model Download | **Rate Limit Only**. Adding `HF_TOKEN` prevents temporary download blocks from HF servers. |
| **Google Gemini** | Cloud API | **Free Tier Quota**. Subject to your Google API Key limits (~15 RPM, 1,500/day). |

## ✨ Key Features

-   **Accurate Transcription**: Uses **faster-whisper** (`large-v2` default for SEA languages) with optimized beam search.
-   **Smart Summarization**: Integrates Google Gemini 2.5 Flash to summarize transcripts into key points (Indonesian).
-   **Large File Support**: Handles audio/video files up to Telegram's limit, and supports **Multi-part ZIP archives** (e.g., `file.zip.001`) for very large files.
-   **GPU Acceleration**: Optimized for fast performance on GPU (CUDA), with FP16/INT8 dynamic loading.
-   **Clean Formatting**: Text output is formatted as **clean paragraphs** separated by double newlines, with timestamps removed for better readability.
-   **Context-Aware**: Uses VAD (Voice Activity Detection) and Repetition Penalties to reduce hallucinations.

## 🚀 How to Run (Google Colab)

The easiest and recommended way is to use Google Colab.

1.  **Setup Secrets**:
    In Google Colab, open the **Secrets** tab (key icon 🔑 on the left sidebar) and add:
    -   `TELEGRAM_BOT_TOKEN`: Bot token from BotFather.
    -   `TELEGRAM_CHAT_ID`: Your Telegram chat ID (for security, the bot only responds to this ID).
    -   `GEMINI_API_KEY`: API Key from Google AI Studio (Optional, for summarization features).
    -   `GITHUB_TOKEN`: GitHub Personal Access Token (Optional, if this repo is Private).
    -   `HF_TOKEN`: Hugging Face Token (Optional, prevents model download rate limits).

2.  **Enable GPU**:
    Ensure the Runtime type is set to **T4 GPU** (Menu: *Runtime > Change runtime type*).

3.  **Run**:
    Copy the code block below into a single cell in your Colab notebook and run it. This script will load your secrets and then execute the runner from the repository.

    ```python
    # @title 🚀 Setup & Run TTB
    import os
    from google.colab import userdata

    # 1. Load Secrets
    for key in ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'GEMINI_API_KEY', 'GITHUB_TOKEN', 'HF_TOKEN']:
        try:
            val = userdata.get(key)
            if val: os.environ[key] = str(val)
        except: pass

    # 2. Run Remote Script
    !curl -s https://raw.githubusercontent.com/arinadi/TTB/main/runner.py -o runner.py && python runner.py
    ```

## 🧠 Smart Mode Selection

TTB automatically detects your environment and selects the best transcription method:

-   **🔥 WHISPER Mode (GPU)**: Activated if a T4/NVIDIA GPU is detected. Highly accurate, runs locally.
-   **🌩️ GEMINI Mode (CPU)**: Default fallback for CPU-only environments (Local/Laptop/Termux). Uses Google Gemini API for transcription. 
    -   *Limit: Max 10 mins per audio file in this mode.*
    -   *Idle timers are extended (5x) to prevent frequent shutdowns on slow systems.*

## 💻 How to Run (Local)

1.  **Clone Repo**:
    ```bash
    git clone https://github.com/arinadi/TTB.git
    cd TTB
    ```

2.  **Install Dependencies**:
    - For **GPU**: `pip install -r requirements.txt`
    - For **CPU**: `pip install -r requirements_cpu.txt`
    - Or run `bash setup_uv.sh` to auto-detect and install.

3.  **Setup Environment Variables**:
    Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `GEMINI_API_KEY`.

4.  **Run Bot**:
    ```bash
    python start.py
    ```

## 📂 File Structure

-   `main.py`: Main entry point. Contains Telegram bot logic, queue system, and model initialization.
-   `config.py`: Centralized configuration and secrets management.
-   `start.py`: Bot manager that handles idle monitoring and auto-restart.
-   `runner.py`: Specialized script for Google Colab automation (cloning, deps, running).
-   `utils.py`: Helper functions for text formatting, logging, and Gemini API wrapper.
-   `gradio_handler.py`: Optional Gradio web interface for large file uploads.
-   `requirements.txt`: Optimized list for Colab (excludes pre-installed libs like `requests`, `httpx`, `tqdm`).
-   `requirements_local.txt`: Full list for local dev.

## 🛠 Advanced Configuration

All settings are managed in `config.py` and can be overridden via Environment Variables:

-   **Model**: `WHISPER_MODEL` (default: `large-v2`).
-   **Precision**: `WHISPER_PRECISION` (`auto`, `float16`, `int8`).
-   **VAD**: `VAD_FILTER` (True/False) to reduce hallucinations.
-   **Decoding**: 
    - `WHISPER_PATIENCE` (Default: 2.0)
    - `REPETITION_PENALTY` (Default: 1.1)
-   **Idle Monitor**: `ENABLE_IDLE_MONITOR` (Colab saver).

## 🔄 Network Resilience

This bot has robust error handling for connection issues in Colab:

-   **Auto-Retry**: Transient network errors are auto-retried (max 2x) without shutdown.
-   **Extended Timeouts**: Optimized specifically for Colab's network environment.
-   **Connection Pool**: Pool size 8 for stable connections.
