# 📰 HeadlineBot: Fast AI Bot for Front-Line Journalists

[![Google Colab](https://img.shields.io/badge/Run%20on-Google%20Colab-orange?logo=googlecolab)](https://colab.research.google.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**HeadlineBot** is an AI assistant for front-line journalists who need fast transcription, instant summaries, and automatic photo color correction — all from Telegram. Powered by **OpenAI Whisper** for accurate transcription, **Google Gemini** for smart summarization, and **Gemma 4** for AI-powered image color correction.

---

## 🚀 One-Click Gourmet Experience (Google Colab)

1.  **Prepare your Secrets** 🔑:
    In Colab's **Secrets** tab, add:
    - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
    - `GEMINI_API_KEY` (Required for summaries and image editing)
    - `HF_TOKEN`, `GITHUB_TOKEN` (Optional for private use/faster downloads)

2.  **Turn on the Stove** 🔥:
    Set Runtime to **T4 GPU** (*Runtime > Change runtime type*).

3.  **Place your Order** 🛎️:
    Copy and run this cell. Your AI chef will be with you in seconds:

    ```python
    # @title 📰 Start HeadlineBot
    import os
    from google.colab import userdata

    # 1. Load Secrets
    for key in ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'GEMINI_API_KEY', 'GITHUB_TOKEN', 'HF_TOKEN']:
        try:
            val = userdata.get(key)
            if val: os.environ[key] = str(val)
        except: pass

    # 2. Start HeadlineBot
    !curl -s https://raw.githubusercontent.com/arinadi/HeadlineBot/main/runner.py -o runner.py && python runner.py
    ```

---

## ⚡ Lightning Fast Service

Forget waiting for heavy AI models to load. HeadlineBot uses a **Microservice-style Startup** optimized for Google Colab:
- **Immediate Greeting**: The bot is online and ready to take your "orders" in **under 10 seconds**.
- **Ready to Serve**: Complete environment setup and AI engine readiness in just **20 seconds**.
- **Background Kitchen Setup**: While your chef greets you, the AI "Kitchen" (Whisper, Torch, & uv) prepares in the background.

---

## ✨ Why Choose HeadlineBot?

| Feature | The HeadlineBot Experience |
| :--- | :--- |
| **🚀 Instant Response** | Micro-startup logic ensures the bot is always ready in **~20 seconds**. |
| **🔥 Unlimited Power** | Runs **OpenAI Whisper** (`large-v2`) locally on Colab's T4 GPU. No duration limits. |
| **🌩️ Cloud Fallback** | No GPU? No problem. HeadlineBot seamlessly switches to **Gemini API** for CPU environments. |
| **🧠 Smart Summary** | Journalist-style summaries in Indonesian with **Gemini 2.5 Flash**. |
| **🎨 Image Color Correction** | AI-powered photo editing using **Gemma 4** - automatic white balance, exposure, and color grading. |
| **📂 Any Format** | Audio, video, images, multi-part ZIPs — HeadlineBot handles it all. |
| **📱 Telegram First** | Send files from your phone, get results back on Telegram — perfect for front-line journalists. |

---

## 🛠️ The Tech Behind the Bot

- **Faster-Whisper**: Optimized for speed and precision using CTranslate2.
- **VAD (Voice Activity Detection)**: Intelligent silence filtering to reduce hallucinations.
- **uv Installer**: Ultra-fast dependency management to get the bot online faster.
- **Resilient Polling**: Advanced error handling for stable connections in Colab.
- **Gemma 4 Image Editor**: AI-powered color correction with Gray World white balance, contrast LUT, and quality guards.
- **OpenCV Pipeline**: Professional-grade image processing with brightness, contrast, saturation, vibrance, clarity, and sharpness adjustments.

---

## 📂 File Structure

- `main.py`: Core bot logic, Telegram handlers, and job worker.
- `runner.py`: Colab entry point — clones repo, installs deps, launches bot.
- `start.py`: Environment detection — sets GPU/CPU mode.
- `utils.py`: Formatting, summarization, and Gemini API wrappers.
- `image_editor.py`: AI-powered image color correction with Gemma 4 + OpenCV.
- `gradio_handler.py`: Optional web UI for large file uploads.
- `bot_classes.py`: Data structures — `JobManager`, `FilesHandler`.

---

## 💻 Local Setup

Prefer to host yourself?
```bash
git clone https://github.com/arinadi/HeadlineBot.git
cd HeadlineBot
bash setup_uv.sh  # Auto-detects hardware and installs everything
python start.py
```

---

*”Fast transcription, instant summaries, color-corrected photos — for front-line journalists who need results now.”* 📰✨
