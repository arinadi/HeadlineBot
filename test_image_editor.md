# 🧪 Quick Test — Image Editor Pipeline (Single Cell)

> Paste ke **1 cell Colab** → jalankan → langsung keluar hasil.
> Input: 5 Google Drive share URLs (1 mandatory, 4 optional).

---

```python
# ╔══════════════════════════════════════════════════════════════════╗
# ║  🧪 IMAGE EDITOR PIPELINE — QUICK TEST (SINGLE CELL)           ║
# ║  Input: Google Drive share URLs  |  Output: side-by-side plot  ║
# ╚══════════════════════════════════════════════════════════════════╝

import os, io, json, asyncio, re, sys, cv2
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from PIL import Image
from pathlib import Path
from IPython.display import display, HTML

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⚙️  CONFIG — Edit bagian ini saja
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GOOGLE_API_KEY = "YOUR_API_KEY_HERE"  # ← PASTE API KEY DARI aistudio.google.com

URLS = {
    "url_1": "https://drive.google.com/file/d/REPLACE_ME_1/view?usp=sharing",  # ← MANDATORY
    "url_2": "",  # optional
    "url_3": "",  # optional
    "url_4": "",  # optional
    "url_5": "",  # optional
}

# Path image_editor.py di Colab (default: /content/)
EDITOR_DIR = "/content"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📦  SETUP & INSTALL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

!pip install opencv-python-headless Pillow matplotlib gdown google-genai -q

sys.path.insert(0, EDITOR_DIR)
from image_editor import analyze_image, apply_corrections

from google import genai
import gdown

print("✅ Setup complete")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔑  VALIDATE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

assert GOOGLE_API_KEY and "YOUR_API_KEY" not in GOOGLE_API_KEY, \
    "❌ Isi GOOGLE_API_KEY dulu di bagian CONFIG!"
assert URLS["url_1"] and "REPLACE_ME" not in URLS["url_1"], \
    "❌ URL #1 mandatory! Paste Google Drive share link di CONFIG!"

active_urls = {k: v for k, v in URLS.items() if v and "REPLACE_ME" not in v}
print(f"📋 {len(active_urls)} URL aktif dari 5")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⬇️  DOWNLOAD FROM GOOGLE DRIVE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def drive_file_id(url: str) -> str:
    """Extract file ID dari berbagai format Google Drive URL."""
    for pattern in [
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"[?&]id=([a-zA-Z0-9_-]+)",
        r"/uc\?.*id=([a-zA-Z0-9_-]+)",
    ]:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    raise ValueError(f"Cannot extract file ID from: {url}")

os.makedirs("/content/test_images", exist_ok=True)
downloaded = {}

for label, url in active_urls.items():
    try:
        file_id = drive_file_id(url)
        out = f"/content/test_images/{label}.jpg"
        gdown.download(id=file_id, output=out, quiet=True)
        if os.path.getsize(out) > 0:
            downloaded[label] = out
            print(f"  ✅ {label}")
        else:
            print(f"  ⚠️ {label}: empty file")
    except Exception as e:
        print(f"  ❌ {label}: {e}")

assert len(downloaded) >= 1, "❌ Tidak ada gambar ter-download!"
print(f"📦 {len(downloaded)} images siap")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🚀  RUN PIPELINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

client = genai.Client(api_key=GOOGLE_API_KEY)
results = {}

for label, input_path in downloaded.items():
    print(f"\n{'─'*50}")
    print(f"🖼️  {label}")

    output_path = f"/content/test_images/{label}_edited.jpg"

    # Two-pass analyze
    params = analyze_image(input_path, client)
    cond = params.get("condition", "?")
    desc = params.get("description", "")
    print(f"  Condition : {cond}")
    print(f"  Description: {desc}")
    print(f"  b={params.get('brightness',0):+d} c={params.get('contrast',1.0):.2f} "
          f"s={params.get('saturation',1.0):.2f} v={params.get('vibrance',1.0):.2f}")

    # Apply corrections
    apply_corrections(input_path, params, output_path)

    results[label] = {"input": input_path, "output": output_path, "params": params}
    print(f"  ✅ → {output_path}")

print(f"\n{'━'*50}")
print(f"✅ Pipeline selesai: {len(results)} images")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📊  SIDE-BY-SIDE COMPARISON + PARAM BAR CHART
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PARAM_RANGES = {
    "brightness": (-80, 80), "contrast": (0.6, 2.0), "saturation": (0.5, 2.0),
    "vibrance": (0.8, 2.0), "highlights": (-80, 20), "shadows": (-20, 80),
    "blacks": (-60, 15), "whites": (0, 60), "warmth": (-40, 40),
    "tint": (-30, 30), "sharpness": (0.5, 2.0), "clarity": (-20, 60),
}
PARAM_SHORT = ["brightness", "contrast", "saturation", "vibrance",
               "highlights", "shadows", "blacks", "whites",
               "warmth", "tint", "sharpness", "clarity"]

n = len(results)
fig = plt.figure(figsize=(18, 6 * n))
gs = gridspec.GridSpec(n, 3, width_ratios=[1, 1, 0.5], wspace=0.12, hspace=0.25)

for i, (label, r) in enumerate(results.items()):
    p = r["params"]
    cond = p.get("condition", "?")
    desc = p.get("description", "")

    # ── Original ──
    ax_orig = fig.add_subplot(gs[i, 0])
    orig_rgb = cv2.cvtColor(cv2.imread(r["input"]), cv2.COLOR_BGR2RGB)
    ax_orig.imshow(orig_rgb)
    ax_orig.set_title(f"ORIGINAL — {label}", fontsize=11, fontweight="bold")
    ax_orig.axis("off")

    # ── Corrected ──
    ax_edit = fig.add_subplot(gs[i, 1])
    edit_rgb = cv2.cvtColor(cv2.imread(r["output"]), cv2.COLOR_BGR2RGB)
    ax_edit.imshow(edit_rgb)
    ax_edit.set_title(f"CORRECTED — [{cond}]", fontsize=11, fontweight="bold", color="green")
    ax_edit.axis("off")

    # ── Param Bar Chart ──
    ax_param = fig.add_subplot(gs[i, 2])
    vals, names, colors = [], [], []
    for name in PARAM_SHORT:
        v = p.get(name, 0)
        lo, hi = PARAM_RANGES[name]
        norm_v = (v - lo) / (hi - lo) if hi != lo else 0.5
        vals.append(norm_v)
        names.append(name[:4])
        colors.append("#2ecc71" if 0.35 <= norm_v <= 0.65 else "#e74c3c")

    ax_param.barh(names, vals, color=colors, edgecolor="white", height=0.6)
    ax_param.axvline(0.5, color="gray", linestyle="--", alpha=0.5, label="neutral")
    ax_param.set_xlim(0, 1)
    ax_param.set_title("Param Profile", fontsize=9)
    ax_param.legend(fontsize=7, loc="lower right")
    ax_param.invert_yaxis()

    # ── Description below corrected image ──
    ax_edit.text(0.5, -0.04, desc, transform=ax_edit.transAxes,
                 ha="center", fontsize=8, style="italic", color="#555")

plt.suptitle("Image Editor Pipeline — Before vs After", fontsize=14, fontweight="bold", y=1.01)
plt.savefig("/content/comparison.png", dpi=150, bbox_inches="tight")
plt.show()
print("💾 /content/comparison.png")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📋  PARAMETER TABLE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

header = ["Label", "Cond", "B", "C", "S", "V", "H", "D", "K", "N", "W", "T", "P", "L", "Desc"]
html = '<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;font-family:monospace;font-size:12px;">'
html += '<tr style="background:#333;color:white;">' + "".join(f"<th>{h}</th>" for h in header) + "</tr>"

for label, r in results.items():
    p = r["params"]
    row = [
        f"<b>{label}</b>",
        f"<b>{p.get('condition','?')}</b>",
        f"{p.get('brightness',0):+d}",
        f"{p.get('contrast',1.0):.2f}",
        f"{p.get('saturation',1.0):.2f}",
        f"{p.get('vibrance',1.0):.2f}",
        f"{p.get('highlights',0):+d}",
        f"{p.get('shadows',0):+d}",
        f"{p.get('blacks',0):+d}",
        f"{p.get('whites',0):+d}",
        f"{p.get('warmth',0):+d}",
        f"{p.get('tint',0):+d}",
        f"{p.get('sharpness',1.0):.2f}",
        f"{p.get('clarity',0):+d}",
        f"{p.get('description','')}",
    ]
    html += "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"

html += "</table>"
display(HTML(html))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📥  DOWNLOAD HASIL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from google.colab import files as colab_files

for label, r in results.items():
    if os.path.exists(r["output"]):
        colab_files.download(r["output"])

if os.path.exists("/content/comparison.png"):
    colab_files.download("/content/comparison.png")

print("\n🎉 Selesai! Semua hasil sudah didownload.")
```

---

## Quick Reference

| Sym | Param | Range |
|-----|-------|-------|
| `b` | brightness | -80..+80 |
| `c` | contrast | 0.6..2.0 |
| `s` | saturation | 0.5..2.0 |
| `v` | vibrance | 0.8..2.0 |
| `h` | highlights | -80..+20 |
| `d` | shadows | -20..+80 |
| `k` | blacks | -60..+15 |
| `n` | whites | 0..+60 |
| `w` | warmth | -40..+40 |
| `t` | tint | -30..+30 |
| `p` | sharpness | 0.5..2.0 |
| `l` | clarity | -20..+60 |

**Condition Codes:** DAYLIGHT · OVERCAST · LOWLIGHT · BACKLIGHT · GOLDEN_HR · HIGH_KEY · GREEN_SPILL · GREEN_CAST · NEON · PORTRAIT · SKIN_WARM · SKIN_PALE · WINDOW_LIGHT · NIGHT · HAZE · BLUE_SKY_SPILL
