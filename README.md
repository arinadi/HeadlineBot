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

## 🔐 Secrets: Satu File `.env`

Semua secret ada di **satu file `.env`** (sudah di-`.gitignore`, tidak pernah masuk repo). Salin `.env.example` → `.env`, lalu isi:

| Variable | Keterangan |
| :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Dari @BotFather (**wajib**) |
| `TELEGRAM_CHAT_ID` | ID chat yang dilayani bot (**wajib**) |
| `OPENAI_COMPAT_API_KEY` | API key OpenCode — ringkasan, retouch, koreksi foto |
| `GEMINI_API_KEY` | Transkripsi mode CPU (opsional) |
| `HF_TOKEN` | Hugging Face, mempercepat download model Whisper (opsional) |

- **VPS / colab CLI** (Opsi C): file `.env` dipakai langsung, di-upload ke VM oleh `colab-run.sh`.
- **Notebook web** (Opsi A/B): jadikan satu secret **`HEADLINEBOT_ENV`** berisi base64 dari `.env`:

```powershell
# PowerShell (Windows) — hasil langsung masuk clipboard
[Convert]::ToBase64String([IO.File]::ReadAllBytes(".env")) | Set-Clipboard
```

```bash
base64 -w0 .env    # Linux
base64 -i .env     # macOS
```

Tempel hasilnya sebagai secret `HEADLINEBOT_ENV` (Colab: tab 🔑 Secrets, aktifkan *Notebook access*; Kaggle: Add-ons → Secrets). Ulangi setiap `.env` berubah.

> Base64 hanya membungkus file jadi satu baris — **bukan enkripsi**. Yang melindungi secret-mu adalah penyimpanan Secrets Colab/Kaggle. Jangan tempel nilainya di kode atau chat.

---

## 🚀 Mulai

### Opsi A: Google Colab

1. Tambahkan secret `HEADLINEBOT_ENV` (lihat di atas).
2. *Runtime > Change runtime type* → **T4 GPU**.
3. Jalankan:

```python
# 📰 HeadlineBot — Colab Edition
import os, subprocess, urllib.request
from google.colab import userdata

VERSION = 'prod'  # ← 'prod' atau 'beta'
os.environ['HEADLINEBOT_VERSION'] = VERSION
os.environ['HEADLINEBOT_ENV'] = userdata.get('HEADLINEBOT_ENV')
_branch = 'beta' if VERSION == 'beta' else 'main'
urllib.request.urlretrieve(f'https://raw.githubusercontent.com/arinadi/HeadlineBot/{_branch}/runner.py', 'runner.py')

proc = subprocess.Popen(['python', 'runner.py'], stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, bufsize=1, text=True)
for line in proc.stdout:
    print(line, end='', flush=True)
```

### Opsi B: Kaggle

1. Tambahkan secret `HEADLINEBOT_ENV` (Add-ons → Secrets).
2. *Settings > Accelerator* → **GPU T4 x2**; *Settings > Internet* → **on**.
3. Jalankan:

```python
# 📰 HeadlineBot — Kaggle Edition
import os, subprocess, urllib.request
from kaggle_secrets import UserSecretsClient

VERSION = 'prod'  # ← 'prod' atau 'beta'
os.environ['HEADLINEBOT_VERSION'] = VERSION
os.environ['HEADLINEBOT_ENV'] = UserSecretsClient().get_secret('HEADLINEBOT_ENV')
_branch = 'beta' if VERSION == 'beta' else 'main'
urllib.request.urlretrieve(f'https://raw.githubusercontent.com/arinadi/HeadlineBot/{_branch}/runner.py', 'runner.py')

proc = subprocess.Popen(['python', 'runner.py'], stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, bufsize=1, text=True)
for line in proc.stdout:
    print(line, end='', flush=True)
```

> **Catatan Kaggle:** idle monitor mematikan bot saat idle; maksimal eksekusi ~9-12 jam per sesi.

**Selesai.** Buka Telegram, kirim file, dan saksikan.

### Opsi C: VPS + colab CLI (bangun otomatis)

Server kecil (Ubuntu, RAM 1 GB cukup) menjalankan **launcher** yang selalu hidup:

- Saat bot mati, launcher mendengarkan chat-mu.
- Pesan/file pertama → launcher membalas "⏰ Waking up...", `git pull`, lalu menyalakan Colab **T4** lewat colab CLI (~2-3 menit). Pesan itu **tidak hilang**: bot di Colab yang memprosesnya.
- Setelah idle, bot mematikan VM dan launcher kembali mendengarkan.

Selama VM hidup, launcher diam (Telegram hanya mengizinkan satu pembaca update per bot).

**1. Install (sekali)**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # uv menyediakan Python 3.12+ untuk colab CLI
uv tool install google-colab-cli
git clone https://github.com/arinadi/HeadlineBot.git ~/HeadlineBot
cd ~/HeadlineBot && git checkout main              # atau beta
cp .env.example .env && nano .env                  # isi secrets (lihat bagian Secrets)
colab sessions                                     # login sekali: buka URL, tempel kode
```

**2. Jalankan launcher sebagai service**

```bash
sudo cp deploy/headlinebot-launcher@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now headlinebot-launcher@$USER
journalctl -u headlinebot-launcher@$USER -f        # lihat log launcher
```

Service menjalankan `python3 launcher.py --version prod --gpu T4` dari `~/HeadlineBot` (ubah di file service untuk `beta`).

**Perintah manual** (tanpa launcher):

```bash
./colab/colab-run.sh up --gpu T4 --version beta    # nyalakan VM + bot
./colab/colab-run.sh logs                          # ekor bot.log di VM
./colab/colab-run.sh stop                          # lepas VM
```

> colab CLI hanya jalan di Linux/macOS (tidak di Windows). `google.colab userdata.get()` tidak berfungsi di sesi CLI, karena itu `.env` di-upload langsung ke `/content/.env`. `bootstrap.py` di VM: ekstrak tarball → muat `.env` → install deps → jalankan bot.

---

## 🧠 Apa yang Bisa HeadlineBot?

### 🎙️ Transkripsi Cepat
Kirim audio atau video. HeadlineBot mengubahnya menjadi teks lengkap tanpa timestamp.
- **GPU Mode**: Whisper large-v2 — akurasi tinggi, tanpa batas durasi
- **CPU Mode**: Gemini Cloud — otomatis pilih model terbaru, maks 20 menit per file (juga dipakai otomatis jika Whisper gagal dimuat)
- **Format**: MP3, MP4, WAV, M4A, WEBM, OGG, FLAC, MKV

> Fitur AI di bawah (ringkasan, koreksi foto, retouch) aktif hanya jika `ENABLE_AI_FEATURES=true` dan provider AI-nya siap (lihat [Provider AI](#provider-ai)). Default: mati — foto dikirim balik apa adanya.

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
- **Preset per kondisi** (`presets.json`): AI mengklasifikasi kondisi foto (BACKLIGHT, LOWLIGHT, PORTRAIT, ...), lalu menyetel preset-nya dengan batas parameter yang terkunci
- **OpenCV Pipeline**: White balance → Brightness → Contrast → Highlights/Shadows → Saturation → Vibrance → Clarity/Sharpness
- **Quality Guard**: Jika hasil koreksi rusak (terlalu terang atau datar), foto original yang dikirim

### 🔧 Retouch Transkrip
Transkrip Whisper → diperbaiki typonya, tanda baca, dan paragraph breaks otomatis via Gemma 4.

### 📁 Multi-Part ZIP
Kirim arsip ZIP berpartisi (.zip.01, .zip.02, dst). HeadlineBot akan:
1. Menggabungkan semua part secara otomatis
2. Mengekstrak file audio dari dalamnya (arsip dengan path berbahaya, symlink, atau > 2 GB setelah ekstrak ditolak)
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

---

## 🛠️ Tech Stack

- **faster-whisper** (Whisper di CTranslate2) — Transkripsi suara, berjalan lokal di GPU
- **Google Gemini** — Ringkasan cerdas & transkripsi cloud fallback
- **Gemma 4** — Analisis warna foto dengan AI
- **Smart Model Manager** — Auto-detect model tersedia, sort by versi, primary + fallback chain
- **OpenCV** — Pipeline koreksi warna profesional
- **python-telegram-bot** — Handler Telegram async yang stabil

---
## 📂 File Structure


```
HeadlineBot/
├── headlinebot/           # Package — semua library bot
│   ├── __init__.py
│   ├── bot_classes.py     # JobManager, IdleMonitor, FilesHandler
│   ├── config.py          # Konfigurasi via environment variables
│   ├── model_manager.py   # Smart model discovery — auto-detect flash/gemma
│   ├── image_editor.py    # AI color correction pipeline (Gemma 4 + OpenCV)
│   └── utils.py           # Summarization, retouch, formatting, platform detection
├── tests/                 # pytest (jalan di CI)
├── main.py                # Core bot — handlers, queue, worker
├── start.py               # GPU/CPU detection, launcher
├── runner.py              # Entry point (web: clone/update; CLI: in-place)
├── launcher.py            # VPS: bangunkan Colab saat ada pesan (Opsi C)
├── deploy/                # systemd service untuk launcher
├── colab/                 # colab-CLI support: colab-run.sh + bootstrap.py
├── presets.json           # Preset & parameter lock koreksi warna per kondisi foto
├── agent.md               # Konteks untuk AI coding agent
├── pyproject.toml         # Konfigurasi ruff & pytest
├── requirements.txt       # GPU: requirements_cpu.txt + faster-whisper
├── requirements_cpu.txt   # CPU: semua yang di-import main.py
└── requirements-dev.txt   # CPU + ruff + pytest
```

---

## 💻 Local Setup

```bash
git clone https://github.com/arinadi/HeadlineBot.git
cd HeadlineBot
pip install -r requirements.txt
python start.py
```

> **Local mode**: set variabel dari `.env` (minimal `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) di environment sebelum `python start.py`.

---

## ⚙️ Konfigurasi

### Bot Settings

| Variable | Default | Keterangan |
| :--- | :--- | :--- |
| `HEADLINEBOT_VERSION` | `prod` | Versi: `prod` (branch main) atau `beta` (branch beta) |
| `ENABLE_AI_FEATURES` | `false` | Aktifkan ringkasan, retouch, dan koreksi foto (nama lama `ENABLE_GEMINI_FEATURES` masih berlaku) |
| `LLM_PROVIDER` | `gemini` | Provider untuk ringkasan, retouch, dan foto: `gemini` atau `openai_compat` |
| `MODEL_SIZE` | `large-v2` | Whisper model size |
| `BOT_FILESIZE_LIMIT` | `20` | Max MB per file |
| `ENABLE_IDLE_MONITOR` | `True` | Auto-shutdown saat idle (hemat Colab/Kaggle credits) |

### Provider AI

Ringkasan, retouch, dan analisis foto memakai satu provider, dipilih lewat `LLM_PROVIDER`. Transkripsi tidak ikut: tetap Whisper (GPU) atau Gemini (CPU).

- `gemini` (default): Gemini/Gemma via `GEMINI_API_KEY`, model dipilih otomatis (lihat catatan di bawah).
- `openai_compat`: API apa pun yang kompatibel dengan OpenAI Chat Completions, misalnya **OpenCode Go**. Model dicoba berurutan; jika satu gagal, lanjut ke berikutnya.

| Variable | Default | Keterangan |
| :--- | :--- | :--- |
| `OPENAI_COMPAT_API_KEY` | — | API key (secret, di `.env`) |
| `OPENAI_COMPAT_BASE_URL` | `https://opencode.ai/zen/go/v1` | Base URL API |
| `OPENAI_COMPAT_MODELS` | `deepseek-v4.1-flash,kimi-k3` | Model teks (ringkasan, retouch), dipisah koma |
| `OPENAI_COMPAT_VISION_MODELS` | `deepseek-v4.1-flash,glm-5.3-flash` | Model yang bisa membaca gambar (koreksi foto) |

> **OpenCode Go:** request dikirim dengan User-Agent `HeadlineBot` dan header `x-opencode-session` (satu ID per job), keduanya diwajibkan OpenCode. Ketentuan Go menyebut layanan ini untuk trafik *coding agent* dan trafik dipantau — pemakaian untuk bot ini bisa ditandai. Cek model yang bisa baca gambar di [models.dev](https://models.dev).

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

### Lint & Test

CI (GitHub Actions, Python 3.12) menjalankan hal yang sama di setiap push/PR ke `main` dan `beta`:

```bash
pip install -r requirements-dev.txt
ruff check .
python -m compileall -q .
pytest -q
```

### Alur Branch

Perubahan masuk ke `beta` dulu, dites di Colab dengan `VERSION = 'beta'`, lalu `main` di-fast-forward ke `beta`.

---

**HeadlineBot** — *Your story is breaking. Your AI is ready.* 📰⚡
