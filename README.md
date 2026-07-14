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

## 🔐 Setup Infisical

HeadlineBot menggunakan [Infisical Cloud](https://app.infisical.com) untuk manajemen secret yang terpusat dan terenkripsi end-to-end.

**Keuntungan:**
- Cukup simpan **4 secret** di Kaggle/Colab (bukan 5)
- Update secret di satu tempat, otomatis berlaku di semua notebook
- Audit log — siapa akses secret, kapan, dari mana
- E2E encrypted — bahkan Infisical tidak bisa baca valuemu

### Setup Sekali Saja

1. **Buat akun** di [app.infisical.com/signup](https://app.infisical.com/signup) (gratis)
2. **Buat Project** baru (misal: `headlinebot`)
3. **Tambahkan secrets** via dashboard:
   - `TELEGRAM_BOT_TOKEN` — dari @BotFather
   - `TELEGRAM_CHAT_ID` — ID chat Telegrammu
   - `GEMINI_API_KEY` — untuk ringkasan & koreksi warna
   - `GITHUB_TOKEN` — untuk clone private repo (opsional)
   - `HF_TOKEN` — Hugging Face token (opsional)
4. **Buat Machine Identity**: Organization Settings → Machine Identities → New → **Universal Auth**
5. **Simpan** `CLIENT_ID` dan `CLIENT_SECRET` (tampil sekali saja!)
6. **Assign** Machine Identity ke project, permission: **Read Only**

### Setiap Notebook Baru

Simpan 4 secret di Kaggle/Colab:
- `INFISICAL_CLIENT_ID` — dari step 5 di atas
- `INFISICAL_CLIENT_SECRET` — dari step 5 di atas
- `INFISICAL_PROJECT_ID` — dari URL project: `app.infisical.com/project/XXX/secrets`
- `INFISICAL_ENV` — `dev`, `staging`, atau `prod`

---

## 🚀 Mulai dalam 3 Langkah

HeadlineBot berjalan di **Google Colab** dan **Kaggle** — pilih salah satu:

### Opsi A: Google Colab

**1. Siapkan Secret**
Di Colab tab **Secrets** (ikon kunci 🔑), tambahkan:
- `INFISICAL_CLIENT_ID` — dari Infisical dashboard (Machine Identity)
- `INFISICAL_CLIENT_SECRET` — dari Infisical dashboard (simpan sekali!)
- `INFISICAL_PROJECT_ID` — dari URL Infisical: `app.infisical.com/project/XXX/secrets`
- `INFISICAL_ENV` — environment: `dev`, `staging`, atau `prod`

> 💡 Semua secret (TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, dll) disimpan di **Infisical Cloud** — satu tempat terpusat, terenkripsi E2E.

**2. Set GPU**
*Runtime > Change runtime type* → pilih **T4 GPU**

**3. Jalankan**

```python
# 📰 HeadlineBot — Your AI Journalist Assistant — Colab Edition
import os, subprocess, urllib.request

# ── Set Versi ──
VERSION = 'prod'  # ← 'prod' atau 'beta'
os.environ['HEADLINEBOT_VERSION'] = VERSION
_branch = 'beta' if VERSION == 'beta' else 'main'
_base = f'https://raw.githubusercontent.com/arinadi/HeadlineBot/{_branch}'

# ── Load Secrets dari Infisical ──
print("🔐 Loading secrets from Infisical...")
import requests
from google.colab import userdata

_login = requests.post("https://app.infisical.com/api/v1/auth/universal-auth/login",
    json={"clientId": userdata.get("INFISICAL_CLIENT_ID"),
          "clientSecret": userdata.get("INFISICAL_CLIENT_SECRET")}).json()
_token = _login["accessToken"]

_resp = requests.get("https://app.infisical.com/api/v4/secrets",
    headers={"Authorization": f"Bearer {_token}"},
    params={"projectId": userdata.get("INFISICAL_PROJECT_ID"),
            "environment": userdata.get("INFISICAL_ENV") or "dev",
            "secretPath": "/", "viewSecretValue": "true"}).json()
for s in _resp["secrets"]:
    os.environ[s["secretKey"]] = s["secretValue"]
print(f"✅ {len(_resp['secrets'])} secrets loaded: {[k for k in ['TELEGRAM_BOT_TOKEN','GEMINI_API_KEY'] if os.environ.get(k)]}")
os.environ['SECRETS_LOADED'] = '1'

# ── Download & Jalankan Runner ──
urllib.request.urlretrieve(f'{_base}/runner.py', 'runner.py')
print(f'✅ runner.py [{_branch}] loaded')

proc = subprocess.Popen(['python', 'runner.py'],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    bufsize=1, universal_newlines=True)
for line in proc.stdout:
    print(line, end='', flush=True)
```

### Opsi B: Kaggle

**1. Siapkan Secret**
Di Kaggle notebook menu **Add-ons > Secrets** (atau panel kiri), tambahkan:
- `INFISICAL_CLIENT_ID` — dari Infisical dashboard (Machine Identity)
- `INFISICAL_CLIENT_SECRET` — dari Infisical dashboard (simpan sekali!)
- `INFISICAL_PROJECT_ID` — dari URL Infisical: `app.infisical.com/project/XXX/secrets`
- `INFISICAL_ENV` — environment: `dev`, `staging`, atau `prod`

> 💡 Semua secret (TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, dll) disimpan di **Infisical Cloud** — satu tempat terpusat, terenkripsi E2E.

**2. Set GPU & Internet**
*Settings > Accelerator* → pilih **GPU T4 x2**
*Settings > Internet* → nyalakan **Allow internet access**

**3. Jalankan**

```python
# 📰 HeadlineBot — Your AI Journalist Assistant — Kaggle Edition
import os, subprocess, urllib.request

# ── Set Versi ──
os.environ['HEADLINEBOT_VERSION'] = VERSION
_branch = 'beta' if VERSION == 'beta' else 'main'
_base = f'https://raw.githubusercontent.com/arinadi/HeadlineBot/{_branch}'

# ── Load Secrets dari Infisical ──
print("🔐 Loading secrets from Infisical...")
import requests
from kaggle_secrets import UserSecretsClient
_secrets = UserSecretsClient()

_login = requests.post("https://app.infisical.com/api/v1/auth/universal-auth/login",
    json={"clientId": _secrets.get_secret("INFISICAL_CLIENT_ID"),
          "clientSecret": _secrets.get_secret("INFISICAL_CLIENT_SECRET")}).json()
_token = _login["accessToken"]

_resp = requests.get("https://app.infisical.com/api/v4/secrets",
    headers={"Authorization": f"Bearer {_token}"},
    params={"projectId": _secrets.get_secret("INFISICAL_PROJECT_ID"),
            "environment": _secrets.get_secret("INFISICAL_ENV") or "dev",
            "secretPath": "/", "viewSecretValue": "true"}).json()
for s in _resp["secrets"]:
    os.environ[s["secretKey"]] = s["secretValue"]
print(f"✅ {len(_resp['secrets'])} secrets loaded: {[k for k in ['TELEGRAM_BOT_TOKEN','GEMINI_API_KEY'] if os.environ.get(k)]}")
os.environ['SECRETS_LOADED'] = '1'

# ── Download & Jalankan Runner ──
urllib.request.urlretrieve(f'{_base}/runner.py', 'runner.py')
print(f'✅ runner.py [{_branch}] loaded')

proc = subprocess.Popen(['python', 'runner.py'],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    bufsize=1, universal_newlines=True)
for line in proc.stdout:
    print(line, end='', flush=True)
```

> **Catatan Kaggle:**
> - Edit `VERSION`, `PROJECT_ID`, `ENVIRONMENT` di atas, lalu run cell (Shift+Enter).
> - HeadlineBot otomatis memuat semua secrets dari Infisical Cloud.
> - Idle monitor aktif — bot mati otomatis saat idle (hemat GPU credits).
> - Maksimal eksekusi ~9-12 jam per sesi.

**Selesai.** Buka Telegram, kirim file, dan saksikan.

---

## 🧠 Apa yang Bisa HeadlineBot?

### 🎙️ Transkripsi Cepat
Kirim audio atau video. HeadlineBot mengubahnya menjadi teks lengkap tanpa timestamp.
- **GPU Mode**: Whisper large-v2 — akurasi tinggi, tanpa batas durasi
- **CPU Mode**: Gemini Cloud — otomatis pilih model terbaru (fallback otomatis jika Whisper gagal download)
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
├── headlinebot/           # Package — semua library bot
│   ├── __init__.py
│   ├── bot_classes.py     # JobManager, IdleMonitor, FilesHandler
│   ├── config.py          # Konfigurasi via environment variables
│   ├── secrets.py         # Infisical Cloud secret management (E2E encrypted)
│   ├── model_manager.py   # Smart model discovery — auto-detect flash/gemma
│   ├── image_editor.py    # AI color correction pipeline (Gemma 4 + OpenCV)
│   ├── gradio_handler.py  # Web UI untuk file besar
│   └── utils.py           # Summarization, retouch, formatting, platform detection
├── main.py                # Core bot — handlers, queue, worker
├── start.py               # GPU/CPU detection, launcher
├── runner.py              # Colab/Kaggle entry point (branch-aware: prod/beta)
├── requirements.txt       # Dependencies (GPU + CPU)
└── requirements_cpu.txt   # CPU-only dependencies
```

---

## 💻 Local Setup

```bash
git clone https://github.com/arinadi/HeadlineBot.git
cd HeadlineBot
pip install -r requirements.txt
python start.py
```

> **Local mode**: Set `INFISICAL_CLIENT_ID`, `INFISICAL_CLIENT_SECRET`, `INFISICAL_PROJECT_ID`, `INFISICAL_ENV` di environment variables, atau set langsung `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GEMINI_API_KEY`.

---

## ⚙️ Konfigurasi

### Infisical (Recommended)

Semua 4 variable ini disimpan di **Kaggle/Colab Secrets** (sekali saja):

| Variable | Keterangan |
| :--- | :--- |
| `INFISICAL_CLIENT_ID` | Machine Identity credentials |
| `INFISICAL_CLIENT_SECRET` | Machine Identity credentials |
| `INFISICAL_PROJECT_ID` | Dari URL: `app.infisical.com/project/XXX/secrets` |
| `INFISICAL_ENV` | `dev`, `staging`, atau `prod` |

> 💡 Semua secret aplikasi (TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, dll) disimpan di Infisical Cloud. Lihat [Setup Infisical](#-setup-infisical) di bawah.

### Bot Settings

| Variable | Default | Keterangan |
| :--- | :--- | :--- |
| `HEADLINEBOT_VERSION` | `prod` | Versi: `prod` (branch main) atau `beta` (branch beta) |
| `ENABLE_GEMINI_FEATURES` | `false` | Enable summary/retouch/photo *(⚠️ sementara `false`)* |
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
subprocess.run(['ruff', 'check', '.', '--output-format=concise'])
```

> **Kaggle:** Pastikan Internet access diaktifkan di Settings sebelum menjalankan lint.

---

**HeadlineBot** — *Your story is breaking. Your AI is ready.* 📰⚡
