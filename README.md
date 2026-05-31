# 📰 HeadlineBot

### Your Story is Breaking. Your AI is Ready.

**Transkrip instan, ringkasan cerdas, foto berwarna — langsung dari Telegram.**

Kirim file audio, video, atau foto dari ponselmu. HeadlineBot akan mengubahnya menjadi transkrip siap publish, ringkasan jurnalistik, dan foto yang sudah dikoreksi warnanya — dalam hitungan menit, bukan jam.

[![Google Colab](https://img.shields.io/badge/Try%20Now-Colab-orange?logo=googlecolab)](https://colab.research.google.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ⚡ Ini Bukan Bot Biasa

Jurnalis lapangan tidak punya waktu menunggu. HeadlineBot dirancang khusus untukmu:

| Masalahmu | Solusi HeadlineBot |
| :--- | :--- |
| Wawancara 2 jam, harus ditranskrip malam ini | 🎙️ **Transkrip selesai sebelum kamu sampai hotel** — Whisper AI + GPU lokal |
| Butuh ringkasan untuk editor | 📝 **Ringkasan jurnalistik otomatis** — format Fakta Berita, Lead, Body, Narasumber |
| Foto kondisi buruk, cahaya minim | 🎨 **Koreksi warna AI** — white balance, exposure, color grading otomatis |
| File terlalu besar untuk Telegram | 📁 **Multi-part ZIP support** — gabung otomatis, ekstrak audio |
| Bot lambat loading AI | ⚡ **Online dalam 10 detik** — startup mikro, AI load di background |

---

## 🚀 Mulai dalam 3 Langkah

### 1. Siapkan Secret
Di Colab tab **Secrets**, tambahkan:
- `TELEGRAM_BOT_TOKEN` — dari @BotFather
- `TELEGRAM_CHAT_ID` — ID chat Telegrammu
- `GEMINI_API_KEY` — untuk ringkasan & koreksi warna

### 2. Set GPU
*Runtime > Change runtime type* → pilih **T4 GPU**

### 3. Jalankan
```python
import os
from google.colab import userdata

for key in ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'GEMINI_API_KEY', 'GITHUB_TOKEN', 'HF_TOKEN']:
    try:
        val = userdata.get(key)
        if val: os.environ[key] = str(val)
    except: pass

!curl -s https://raw.githubusercontent.com/arinadi/HeadlineBot/main/runner.py -o runner.py && python runner.py
```

**Selesai.** Buka Telegram, kirim file, dan saksikan.

---

## 🧠 Apa yang Bisa HeadlineBot?

### 🎙️ Transkripsi Cepat
Kirim audio atau video. HeadlineBot mengubahnya menjadi teks lengkap tanpa timestamp.
- **GPU Mode**: Whisper large-v2 — akurasi tinggi, tanpa batas durasi
- **CPU Mode**: Gemini Cloud — otomatis fallback jika tidak ada GPU
- **Format**: MP3, MP4, WAV, M4A, WEBM, OGG, FLAC, MKV

### 📝 Ringkasan Jurnalistik
Transkrip 30 menit → ringkasan 1 menit yang siap kirim ke editor:
- **Lead** — inti berita dalam 1-2 kalimat
- **Body** — detail per topik dengan kutipan
- **Narasumber** — nama, jabatan, kutipan kunci
- **Data Pendukung** — angka dan statistik
- **Perlu Klarifikasi** — hal yang masih abu-abu

Semua dalam Bahasa Indonesia, format jurnalistik.

### 🎨 Koreksi Warna Foto
Kirim foto dari lapangan — cahaya minim, warna belang, backlight:
- **Gemma 4 AI** menganalisis foto dan menentukan parameter koreksi
- **OpenCV Pipeline**: White balance → Brightness → Contrast → Saturation → Vibrance → Sharpness
- **Quality Guard**: Jika koreksi memperburuk gambar, foto original tetap dikirim

### 📁 Multi-Part ZIP
Kirim arsip ZIP berpartisi (.zip.01, .zip.02, dst). HeadlineBot akan:
1. Menggabungkan semua part secara otomatis
2. Mengekstrak file audio dari dalamnya
3. Memproses satu per satu ke queue

---

## ⚡ Kenapa HeadlineBot?

| | HeadlineBot | Bot Transkripsi Lain |
| :--- | :--- | :--- |
| **Startup** | ⚡ 10 detik | 🐌 1-3 menit |
| **Transkripsi** | 🎯 Whisper large-v2 (GPU) | 📝 API cloud (bayar per menit) |
| **Ringkasan** | 📰 Format jurnalistik | 📄 Plain text |
| **Foto** | 🎨 Koreksi warna AI | ❌ Tidak ada |
| **Batas Durasi** | ♾️ Tanpa batas (GPU) | ⏱️ 10-60 menit |
| **Harga** | 💰 Gratis (Colab) | 💸 $0.006/menit |
| **Offline** | ✅ GPU local processing | ❌ Selalu online |

---

## 🛠️ Tech Stack

- **OpenAI Whisper** — Transkripsi suara terbaik di dunia, berjalan lokal di GPU
- **Google Gemini** — Ringkasan cerdas & transkripsi cloud fallback
- **Gemma 4** — Analisis warna foto dengan AI
- **OpenCV** — Pipeline koreksi warna profesional
- **python-telegram-bot** — Handler Telegram async yang stabil
- **Gradio** — Web UI alternatif untuk upload file besar

---

## 📂 Struktur Proyek

```
HeadlineBot/
├── main.py              # Core bot — handlers, queue, worker
├── image_editor.py      # AI color correction pipeline (Gemma 4 + OpenCV)
├── bot_classes.py       # JobManager, FilesHandler
├── utils.py             # Summarization, formatting, Gemini API
├── config.py            # Konfigurasi via environment variables
├── start.py             # GPU/CPU detection, launcher
├── runner.py            # Colab entry point
├── gradio_handler.py    # Web UI untuk file besar
├── requirements.txt     # GPU dependencies
└── requirements_cpu.txt # CPU-only dependencies
```

---

## 💻 Local Setup

```bash
git clone https://github.com/arinadi/HeadlineBot.git
cd HeadlineBot
bash setup_uv.sh  # Auto-detect hardware & install
python start.py
```

---

## ⚙️ Konfigurasi

| Variable | Default | Keterangan |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | — | Token dari BotFather (**wajib**) |
| `TELEGRAM_CHAT_ID` | — | ID chat admin (**wajib**) |
| `GEMINI_API_KEY` | — | Google AI Studio key (untuk ringkasan & foto) |
| `MODEL_SIZE` | `large-v2` | Whisper model size |
| `BOT_FILESIZE_LIMIT` | `20` | Max MB per file |
| `ENABLE_IDLE_MONITOR` | `True` | Auto-shutdown saat idle (hemat Colab credits) |
| `GEMMA_MODEL` | `models/gemma-4-26b-a4b-it` | Model untuk analisis warna foto |

---

## 📱 Workflow Jurnalis Lapangan

```
🎤 Wawancara → kirim audio ke Telegram
                    ↓
📝 HeadlineBot transkrip (TS_*.txt)
                    ↓
📰 HeadlineBot ringkasan jurnalistik (AI_*.txt)
                    ↓
📸 Kirim foto → HeadlineBot koreksi warna
                    ↓
✅ Siap kirim ke redaksi
```

---

**HeadlineBot** — *Your story is breaking. Your AI is ready.* 📰⚡
