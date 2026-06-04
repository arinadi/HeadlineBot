# 📋 Audit: Kaggle & Colab Compatibility

> **Date:** 2026-06-04
> **Scope:** Full codebase audit — runtime detection, secrets, output, long-running process

---

## 1. Perubahan yang Sudah Diterapkan

### `main.py` — Kaggle Runtime Detection

```python
# Detect Runtime Environment (Kaggle > Colab > Local)
IS_COLAB = False
IS_KAGGLE = False

try:
    from kaggle_secrets import UserSecretsClient
    IS_KAGGLE = True
    class KaggleRuntime:
        def unassign(self): print("🔌 Kaggle: no auto-shutdown (stop notebook manually)")
    runtime = KaggleRuntime()
except ImportError:
    try:
        from google.colab import runtime
        IS_COLAB = True
    except ImportError:
        class MockRuntime:
            def unassign(self): print("🔌 Local Runtime Shutdown Executed")
        runtime = MockRuntime()
```

- Priority: Kaggle → Colab → Local
- `KaggleRuntime.unassign()` = no-op (Kaggle tidak support auto-shutdown)
- `finally` block handle kedua platform

### `main.py` — Shutdown Flow Fix

```python
async def perform_shutdown(reason: str):
    # 1. Notify admin
    await send_telegram_notification(...)
    # 2. Stop polling (unblocks run_polling)
    await application.stop()
    # 3. Platform-specific termination
    if IS_KAGGLE:
        os._exit(0)        # Force kill — no runtime.unassign()
    elif IS_COLAB:
        runtime.unassign()  # Colab auto-shutdown
    else:
        pass                # Local: exit naturally
```

Sebelumnya: `runtime.unassign()` saja → **no-op di Kaggle, bot tetap hidup**.
Sekarang: `application.stop()` + `os._exit(0)` → **bot benar-benar mati di Kaggle**.

### `runner.py` — Complete Rewrite

- `detect_platform()` → `"kaggle"` | `"colab"` | `"local"`
- `load_secrets()` — Kaggle pakai `UserSecretsClient`, Colab pakai `userdata`
- Git fallback: download ZIP jika `git clone` gagal (Kaggle tanpa git)

### `gemini_transcript.py` — Kaggle Support

- Deteksi `IN_KAGGLE` via `kaggle_secrets` module
- Load API key dari `UserSecretsClient` untuk Kaggle
- `__main__` block handle Kaggle mode

### `test_image_editor.md` — Platform-Aware

- Path dinamis: `WORK_DIR` → `/kaggle/working` atau `/content`
- Download: Colab pakai `files.download()`, Kaggle pakai Output panel

### `README.md` — Kaggle Instructions

- Badge Kaggle ditambahkan
- "Mulai dalam 3 Langkah" dipecah jadi Opsi A (Colab) dan Opsi B (Kaggle)
- Kaggle section pakai `subprocess.Popen` streaming (bukan `!python`)
- Catatan: Kaggle tidak support auto-shutdown, stop manual

### `runner.py` — Output Buffering & Streaming Fix

- `PYTHONUNBUFFERED=1` di-set di awal (paksa unbuffered output)
- `run_command_streaming()` — subprocess streaming real-time untuk Kaggle
- `verify_secrets()` — cek secrets wajib sebelum launch bot
- Semua `print()` pakai `flush=True`
- Kaggle mode pakai streaming, Colab/Local pakai `os.system()`

### `main.py` — Heartbeat Output

- `queue_processor()` punya heartbeat tiap 60 detik
- Log queue status & processing file → prevent Kaggle idle kill
- `asyncio.wait_for()` dengan 30s timeout → loop back ke heartbeat check

---

## 2. Perbedaan Kaggle vs Colab (Detail)

### 🔴 Output Buffering

Di Kaggle, **output Python di-buffer** — `print()` tidak langsung muncul, bahkan kadang tidak muncul sama sekali.

**Solusi:** Paksa flush output:

```python
import sys
print("pesan kamu", flush=True)
sys.stdout.flush()
```

Atau set environment variable di awal cell:

```python
import os
os.environ['PYTHONUNBUFFERED'] = '1'
```

### 🔴 Shell Command Behavior

Kaggle menjalankan shell command (`!`) secara **berbeda dari Colab**:

- Output dari subprocess/shell command sering **tidak di-stream real-time**
- Script yang berjalan lama (seperti bot Telegram) bisa **di-kill otomatis** oleh Kaggle karena dianggap idle

**Solusi — ganti cara run:**

```python
import subprocess, sys

process = subprocess.Popen(
    ['python', 'runner.py'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    bufsize=1,
    universal_newlines=True
)

for line in process.stdout:
    print(line, end='', flush=True)
```

### 🔴 Secrets Access

| | Colab | Kaggle |
|---|---|---|
| Cara akses | `from google.colab import userdata` | `from kaggle_secrets import UserSecretsClient` |
| Lokasi setting | Kunci di sidebar kiri | Add-ons → Secrets |
| Harus aktifkan | Tidak perlu | **Harus centang "Attach to notebook"** |

Kalau secret tidak di-attach, `get_secret()` akan **silent fail** (tidak error, tapi nilai kosong).

**Cek dulu apakah secret terbaca:**

```python
from kaggle_secrets import UserSecretsClient
user_secrets = UserSecretsClient()

try:
    val = user_secrets.get_secret('TELEGRAM_BOT_TOKEN')
    print(f"Token ada: {val[:10]}...", flush=True)
except Exception as e:
    print(f"Gagal baca secret: {e}", flush=True)
```

### 🔴 Long-Running Process

Kaggle **membatasi eksekusi** sekitar **9-12 jam**, dan kalau tidak ada output selama beberapa menit, session bisa dianggap idle dan di-stop.

Untuk bot Telegram yang terus berjalan, Kaggle **bukan tempat ideal** — tapi bisa disiasati dengan output berkala:

```python
# Di dalam loop bot kamu, tambahkan heartbeat
import time
print(f"[{time.strftime('%H:%M:%S')}] Bot masih jalan...", flush=True)
```

### 🔴 `!curl ... && python runner.py`

Di Kaggle, `!curl ... && python runner.py` bisa timeout atau tidak stream output.

**Solusi:** Download file dulu, lalu jalankan via `subprocess.Popen` dengan streaming.

---

## 3. Checklist Sebelum Run di Kaggle

1. ✅ **Secrets sudah di-attach?** → Kaggle → notebook → Add-ons → Secrets → centang semua key
2. ✅ **Internet diaktifkan?** → Settings → Internet → On (perlu verifikasi nomor HP)
3. ✅ **Pakai `flush=True`** di semua print
4. ✅ **Ganti `!python`** dengan `subprocess.Popen` untuk streaming output
5. ✅ **Heartbeat output** agar Kaggle tidak anggap idle

---

## 4. File-by-File Audit Results

| File | Status | Catatan |
|:---|:---|:---|
| `config.py` | ✅ | `os.environ.get()` — universal |
| `utils.py` | ✅ | Via `config.py` — universal |
| `start.py` | ✅ | `nvidia-smi` — universal |
| `bot_classes.py` | ✅ | `os.getenv('TRANSCRIPTION_MODE')` — universal |
| `image_editor.py` | ✅ | Via `config.py` — universal |
| `model_manager.py` | ✅ | Via `genai` client — universal |
| `gradio_handler.py` | ✅ | `os.environ.get()` — universal |
| `main.py` | ✅ | Updated — Kaggle + Colab detection |
| `runner.py` | ✅ | Rewritten — Kaggle + Colab support |
| `gemini_transcript.py` | ✅ | Updated — Kaggle + Colab secrets |
| `test_image_editor.md` | ✅ | Updated — platform-aware paths |
| `README.md` | ✅ | Updated — Kaggle instructions |
| `agent.md` | ✅ | Updated — mentions Kaggle |

---

## 5. Yang Perlu Diperhatikan

### Kaggle Idle Timer

Kaggle bisa stop notebook jika tidak ada output selama beberapa menit. Bot perlu **heartbeat output** di dalam loop utama (`queue_processor` di `main.py`). Lihat task berikutnya.

### Kaggle Execution Limit

Kaggle batas eksekusi ~9-12 jam. Idle monitor sudah handle ini (auto-shutdown setelah idle). Tapi jika bot aktif terus, Kaggle akan kill paksa.

### Kaggle GPU

Kaggle GPU T4 x2 tersedia. `start.py` otomatis deteksi via `nvidia-smi` → mode WHISPER. Tidak perlu perubahan.

### Kaggle Internet

Harus aktifkan manual di Settings. Tanpa internet, bot tidak bisa connect ke Telegram API. `runner.py` sudah handle graceful failure.

---

## 6. Shutdown Flow Fix (Critical)

### Masalah Sebelumnya

Saat idle monitor trigger shutdown:
1. `perform_shutdown()` → `runtime.unassign()` → **no-op di Kaggle**
2. Bot **tetap hidup** — `application.run_polling()` tidak berhenti
3. Idle monitor `continue` (karena `shutdown_imminent = True`)
4. **Result:** Bot idle di Kaggle sampai 60-hour session limit, waste GPU credits

### Fix

`perform_shutdown()` sekarang:
1. Kirim notifikasi Telegram
2. **`await application.stop()`** — hentikan polling loop (unblocks `run_polling()`)
3. Platform-specific: Kaggle → `os._exit(0)`, Colab → `runtime.unassign()`, Local → exit naturally

`__main__` finally block jadi safety net saja (untuk KeyboardInterrupt / normal exit).

### Alur Shutdown yang Benar

```
Idle Monitor (60s loop)
  └─ _handle_shutdown()
       └─ perform_shutdown("Automatic Idle Shutdown")
            ├─ 1. Send Telegram notification
            ├─ 2. await application.stop()  ← stops run_polling()
            └─ 3. Platform termination:
                 ├─ Kaggle: os._exit(0)  ← force kill
                 ├─ Colab: runtime.unassign()
                 └─ Local: process exits naturally
```

## 7. Next Steps

- [x] Tambahkan heartbeat output ke `queue_processor()` di `main.py`
- [x] Update `runner.py` Kaggle section pakai `subprocess.Popen` streaming
- [x] Tambahkan `PYTHONUNBUFFERED=1` di `runner.py`
- [x] Tambahkan secrets verification di `runner.py`
- [x] Fix shutdown flow — `application.stop()` + `os._exit(0)` untuk Kaggle
- [ ] Test full pipeline di Kaggle notebook
