# 📰 HeadlineBot

### Your Story is Breaking. Your AI is Ready.

**Transkrip instan, ringkasan cerdas, foto berwarna — langsung dari Telegram.**

Kirim file audio, video, atau foto dari ponselmu. HeadlineBot akan mengubahnya menjadi transkrip siap publish, ringkasan jurnalistik, dan foto yang sudah dikoreksi warnanya — dalam hitungan menit, bukan jam.

[![Google Colab](https://img.shields.io/badge/Try%20Now-Colab-orange?logo=googlecolab)](https://colab.research.google.com/)
[![Kaggle](https://img.shields.io/badge/Try%20Now-Kaggle-blue?logo=kaggle)](https://www.kaggle.com/)
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

HeadlineBot berjalan di **Google Colab** dan **Kaggle** — pilih salah satu:

### Opsi A: Google Colab

**1. Siapkan Secret**
Di Colab tab **Secrets** (ikon kunci 🔑), tambahkan:
- `TELEGRAM_BOT_TOKEN` — dari @BotFather
- `TELEGRAM_CHAT_ID` — ID chat Telegrammu
- `GEMINI_API_KEY` — untuk ringkasan & koreksi warna

**2. Set GPU**
*Runtime > Change runtime type* → pilih **T4 GPU**

**3. Pilih Versi & Jalankan**

```python
#@title Pilih Versi { display-mode: "form" }
version = "prod" #@param ["prod", "beta"]

import os, subprocess, urllib.request
os.environ['HEADLINEBOT_VERSION'] = version
_branch = 'beta' if version == 'beta' else 'main'

# Load secrets dari Colab
from google.colab import userdata
for key in ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'GEMINI_API_KEY']:
    try:
        val = userdata.get(key)
        if val: os.environ[key] = str(val)
    except Exception: pass

# Download runner
url = f'https://raw.githubusercontent.com/arinadi/HeadlineBot/{_branch}/runner.py'
urllib.request.urlretrieve(url, 'runner.py')
print(f'✅ runner.py [{_branch}] loaded')

# Jalankan
proc = subprocess.Popen(['python', 'runner.py'],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    bufsize=1, universal_newlines=True)
for line in proc.stdout:
    print(line, end='', flush=True)
```

### Opsi B: Kaggle

**1. Siapkan Secret**
Di Kaggle notebook menu **Add-ons > Secrets** (atau panel kiri), tambahkan:
- `TELEGRAM_BOT_TOKEN` — dari @BotFather
- `TELEGRAM_CHAT_ID` — ID chat Telegrammu
- `GEMINI_API_KEY` — untuk ringkasan & koreksi warna

**2. Set GPU & Internet**
*Settings > Accelerator* → pilih **GPU T4 x2**
*Settings > Internet* → nyalakan **Allow internet access**

**3. Pilih Versi & Jalankan**

```python
import os, subprocess, urllib.request
from ipywidgets import Dropdown, Button, Output

# ── Select form ──
sel = Dropdown(options=['prod', 'beta'], value='prod', description='Versi:')
out = Output()
display(sel, out)

def run(b):
    os.environ['HEADLINEBOT_VERSION'] = sel.value
    _branch = 'beta' if sel.value == 'beta' else 'main'

    with out:
        out.clear_output()

        # Load secrets dari Kaggle
        from kaggle_secrets import UserSecretsClient
        client = UserSecretsClient()
        for key in ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'GEMINI_API_KEY']:
            try:
                val = client.get_secret(key)
                if val: os.environ[key] = str(val)
            except Exception: pass

        # Download runner
        url = f'https://raw.githubusercontent.com/arinadi/HeadlineBot/{_branch}/runner.py'
        urllib.request.urlretrieve(url, 'runner.py')
        print(f'✅ runner.py [{_branch}] loaded')

        # Jalankan (streaming)
        proc = subprocess.Popen(['python', 'runner.py'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=1, universal_newlines=True)
        for line in proc.stdout:
            print(line, end='', flush=True)

btn = Button(description='🚀 Jalankan')
btn.on_click(run)
display(btn)
```

> **Catatan Kaggle:**
> - Pilih versi dari dropdown, lalu klik **Jalankan**.
> - HeadlineBot otomatis memuat secrets dari Kaggle Secrets.
> - Idle monitor aktif — bot mati otomatis saat idle (hemat GPU credits).
> - Maksimal eksekusi ~9-12 jam per sesi.

**Selesai.** Buka Telegram, kirim file, dan saksikan.

---

## 🧠 Apa yang Bisa HeadlineBot?

### 🎙️ Transkripsi Cepat
Kirim audio atau video. HeadlineBot mengubahnya menjadi teks lengkap tanpa timestamp.
- **GPU Mode**: Whisper large-v2 — akurasi tinggi, tanpa batas durasi
- **CPU Mode**: Gemini Cloud — otomatis pilih model terbaru, fallback jika credit habis
- **Format**: MP3, MP4, WAV, M4A, WEBM, OGG, FLAC, MKV

### 📝 Ringkasan Jurnalistik
Transkrip 30 menit → ringkasan 1 menit yang siap kirim ke editor. Menggunakan Gemma 4 (atau flash terbaru) via Smart Model Manager:
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

### 🔧 Retouch Transkrip
Transkrip Whisper → diperbaiki typonya, tanda baca, dan paragraph breaks otomatis via Gemma 4.

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
| **Ringkasan** | 📰 Format jurnalistik (Gemma 4) | 📄 Plain text |
| **Retouch** | 🔧 Typo fix + paragraph breaks | ❌ Tidak ada |
| **Foto** | 🎨 Koreksi warna AI | ❌ Tidak ada |
| **Model Management** | 🤖 Auto-detect & sort by version | ⚙️ Hardcoded |
| **Batas Durasi** | ♾️ Tanpa batas (GPU) | ⏱️ 10-60 menit |
| **Harga** | 💰 Gratis (Colab/Kaggle) | 💸 $0.006/menit |
| **Offline** | ✅ GPU local processing | ❌ Selalu online |

---

## 🛠️ Tech Stack

- **OpenAI Whisper** — Transkripsi suara terbaik di dunia, berjalan lokal di GPU
- **Google Gemini** — Ringkasan cerdas & transkripsi cloud fallback
- **Gemma 4** — Analisis warna foto dengan AI
- **Smart Model Manager** — Auto-detect model tersedia, sort by versi, primary + fallback chain
- **OpenCV** — Pipeline koreksi warna profesional
- **python-telegram-bot** — Handler Telegram async yang stabil
- **Gradio** — Web UI alternatif untuk upload file besar

---

## 📂 File Structure

```
HeadlineBot/
├── main.py              # Core bot — handlers, queue, worker
├── model_manager.py     # Smart model discovery — auto-detect flash/gemma, version sort
├── image_editor.py      # AI color correction pipeline (Gemma 4 + OpenCV)
├── bot_classes.py       # JobManager, FilesHandler
├── utils.py             # Summarization, retouch, formatting, Gemini API
├── config.py            # Konfigurasi via environment variables
├── start.py             # GPU/CPU detection, launcher
├── runner.py            # Colab/Kaggle entry point (branch-aware: prod/beta)
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
| `HEADLINEBOT_VERSION` | `prod` | Versi: `prod` (branch main) atau `beta` (branch beta) |
| `TELEGRAM_BOT_TOKEN` | — | Token dari BotFather (**wajib**) |
| `TELEGRAM_CHAT_ID` | — | ID chat admin (**wajib**) |
| `GEMINI_API_KEY` | — | Google AI Studio key (untuk ringkasan, retouch, foto) |
| `MODEL_SIZE` | `large-v2` | Whisper model size |
| `BOT_FILESIZE_LIMIT` | `20` | Max MB per file |
| `ENABLE_IDLE_MONITOR` | `True` | Auto-shutdown saat idle (hemat Colab/Kaggle credits) |

> **Catatan Model:** HeadlineBot menggunakan Smart Model Manager yang otomatis mendeteksi model yang tersedia di akun Gemini-mu, memfilter flash & gemma, dan mengurutkan berdasarkan versi terbaru. Tidak perlu setting manual — model primary dan fallback diatur otomatis!

---

## 📱 Workflow Jurnalis Lapangan

```
🎤 Wawancara → kirim audio ke Telegram
                    ↓
📝 HeadlineBot transkrip (TS_*.txt)
                    ↓
📰 HeadlineBot ringkasan jurnalistik (SM_*.txt)
                    ↓
🔧 HeadlineBot retouch transkrip (RT_*.txt)
                    ↓
📸 Kirim foto → HeadlineBot koreksi warna
                    ↓
✅ Siap kirim ke redaksi
```

---

## 🛠️ Development

### Lint (Colab / Kaggle)

```python
import os, subprocess

# Clone atau pull
if os.path.exists('HeadlineBot'):
    os.chdir('HeadlineBot')
    subprocess.run(['git', 'pull'], check=True)
else:
    subprocess.run(['git', 'clone', 'https://github.com/arinadi/HeadlineBot.git'], check=True)
    os.chdir('HeadlineBot')

# Install & jalankan ruff
subprocess.run(['pip', 'install', 'ruff', '-q'])
subprocess.run(['ruff', 'check', '.', '--fix', '--unsafe-fixes', '--output-format=concise'])
```

> **Kaggle:** Pastikan Internet access diaktifkan di Settings sebelum menjalankan lint.

---

**HeadlineBot** — *Your story is breaking. Your AI is ready.* 📰⚡
