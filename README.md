# 🤵 TTB: Your Professional Transcription Waiter

[![Google Colab](https://img.shields.io/badge/Run%20on-Google%20Colab-orange?logo=googlecolab)](https://colab.research.google.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**TTB (Telegram Transcription Bot)** is not just a tool; it's a premium service for your audio and video files. Powered by **OpenAI Whisper** for world-class transcription and **Google Gemini** for intelligent summarization, TTB delivers results with the elegance and speed of a professional waiter.

---

## 🚀 One-Click Gourmet Experience (Google Colab)

1.  **Prepare your Secrets** 🔑:
    In Colab's **Secrets** tab, add:
    - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
    - `GEMINI_API_KEY` (Optional for summaries)
    - `HF_TOKEN`, `GITHUB_TOKEN` (Optional for private use/faster downloads)

2.  **Turn on the Stove** 🔥:
    Set Runtime to **T4 GPU** (*Runtime > Change runtime type*).

3.  **Place your Order** 🛎️:
    Copy and run this cell. Your professional waiter will be with you in seconds:

    ```python
    # @title 🤵 Start TTB Restaurant
    import os
    from google.colab import userdata

    # 1. Greet the Waiter (Load Secrets)
    for key in ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'GEMINI_API_KEY', 'GITHUB_TOKEN', 'HF_TOKEN']:
        try:
            val = userdata.get(key)
            if val: os.environ[key] = str(val)
        except: pass

    # 2. Open the Restaurant
    !curl -s https://raw.githubusercontent.com/arinadi/TTB/main/runner.py -o runner.py && python runner.py
    ```

---

## ⚡ Lightning Fast "Restaurant" Service

Forget waiting for heavy AI models to load. TTB uses a **Microservice-style Startup** optimized for Google Colab:
- **Immediate Host Greeting**: The bot is online and ready to take your "orders" in **under 10 seconds**.
- **Ready to Serve**: Complete environment setup and AI engine readiness in just **20 seconds**.
- **Background Kitchen Setup**: While your "Waiter" greets you, the AI "Kitchen" (Whisper, Torch, & uv) prepares in the background.

---

## ✨ Why Choose TTB?

| Feature | The TTB Experience |
| :--- | :--- |
| **🚀 Instant Response** | Micro-startup logic ensures the bot is always ready in **~20 seconds**. |
| **🔥 Unlimited Power** | Runs **OpenAI Whisper** (`large-v2`) locally on Colab's T4 GPU. No duration limits. |
| **🌩️ Cloud Fallback** | No GPU? No problem. TTB seamlessly switches to **Gemini API** for CPU environments. |
| **🧠 Smart Summary** | Get the gist instantly with **Gemini 2.5 Flash** summarizing into key points. |
| **📂 Any Format** | Audio, video, multi-part ZIPs—TTB handles it all with professional grace. |
| **🤵 Waiter Persona** | Real-time status updates: *Kitchen heating up... Cooking your file... Order ready!* |

---

## 🛠️ The Tech Behind the Service

- **Faster-Whisper**: Optimized for speed and precision using CTranslate2.
- **VAD (Voice Activity Detection)**: Intelligent silence filtering to reduce hallucinations.
- **uv Installer**: Ultra-fast dependency management to get the bot online faster.
- **Resilient Polling**: Advanced error handling for stable connections in Colab.

---

## 📂 Restaurant Layout (File Structure)

- `main.py`: The **Head Waiter**. Manages the queue and orchestrates service.
- `runner.py`: The **Maitre D'**. Handles environment setup and "Kitchen" preparation.
- `start.py`: The **Manager**. Monitors hardware and ensures smooth operation.
- `utils.py`: The **Sous-Chefs**. Formatters, loggers, and Gemini API wrappers.
- `gradio_handler.py`: The **Web Buffet**. Optional UI for large file uploads.

---

## 💻 Local Dining (Manual Run)

Prefer to host yourself?
```bash
git clone https://github.com/arinadi/TTB.git
cd TTB
bash setup_uv.sh  # Auto-detects hardware and installs everything
python start.py
```

---

*“Transcription is a dish best served fast.”* 🤵✨
