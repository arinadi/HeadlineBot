# Photo Colorize Pipeline — Preset Research & System Prompt Guide

Riset ini mendokumentasikan preset parameter koreksi foto berdasarkan kondisi pencahayaan dan warna,
dirancang untuk pipeline auto-colorize dengan analisis berbasis LLM (Gemma/Gemini + OpenCV).

---

## Arsitektur Pipeline

```
Image → OpenCV Read → Resize 726px → LLM Analyze → JSON Params → OpenCV Apply → Output
```

Masalah utama yang diselesaikan: **inkonsistensi output LLM** akibat kurangnya anchor kondisi spesifik.
Solusi: preset berbasis kondisi foto (seperti Lightroom preset), decision tree eksplisit, dan parameter lock.

---

## Parameter Reference

| Key | Nama          | Range       | Default | Keterangan                                  |
|-----|---------------|-------------|---------|---------------------------------------------|
| `b` | Brightness    | -80 .. 80   | 0       | Offset eksposur keseluruhan                 |
| `c` | Contrast      | 0.6 .. 2.0  | 1.0     | Kekuatan S-curve                            |
| `s` | Saturation    | 0.5 .. 2.0  | 1.0     | Intensitas warna linear                     |
| `v` | Vibrance      | 0.8 .. 2.0  | 1.0     | Boost area saturasi rendah, aman untuk skin |
| `h` | Highlights    | -80 .. 20   | 0       | Recovery (-) atau boost (+) highlight       |
| `d` | Shadows       | -20 .. 80   | 0       | Angkat shadow                               |
| `k` | Blacks        | -60 .. 15   | 0       | Turunkan black point                        |
| `n` | Whites        | 0 .. 60     | 0       | Naikkan white point                         |
| `w` | Warmth        | -40 .. 40   | 0       | Negatif = dingin/biru, positif = hangat/kuning |
| `t` | Tint          | -30 .. 30   | 0       | Negatif = shift hijau, positif = shift magenta |
| `p` | Sharpness     | 0.5 .. 2.0  | 1.0     | Kekuatan unsharp mask                       |
| `l` | Clarity       | -20 .. 60   | 0       | Midtone contrast; negatif = skin soften     |
| `x` | Description   | string      | —       | Diagnosis satu baris, max 12 kata           |

---

## Preset Kondisi Foto

### Kategori 1: Pencahayaan

---

#### P01 — Natural/Outdoor Day
**Kondisi:** Siang hari di luar ruangan, pencahayaan alami merata  
**Diagnosis:** `Balanced daylight, no correction needed`

Baseline preset untuk kondisi ideal. Digunakan jika LLM tidak menemukan masalah spesifik.
Hanya sedikit boost vibrance untuk kedalaman warna.

**Perhatian:**
- Jangan over-correct foto yang sudah bagus
- Gunakan sebagai fallback jika kondisi ambigu

```json
{"b":0,"c":1.05,"s":1.05,"v":1.1,"h":0,"d":0,"k":0,"n":0,"w":0,"t":0,"p":1.0,"l":5,"x":"Balanced daylight, minor vibrance boost"}
```

---

#### P02 — Overcast/Mendung
**Kondisi:** Langit mendung, cahaya flat tanpa bayangan keras  
**Diagnosis:** `Flat light, slight cool cast, low contrast`

Cahaya mendung cenderung flat dan memiliki color temperature dingin (~6500K+).
Naikkan contrast dan warmth ringan. Clarity +10 untuk memunculkan detail yang hilang.

**Perhatian:**
- Jangan over-warm — karakter mendung adalah cool, bukan dingin ekstrem
- Contrast minimal +0.1 dari default agar tidak flat

```json
{"b":5,"c":1.15,"s":1.1,"v":1.15,"h":0,"d":5,"k":0,"n":5,"w":8,"t":0,"p":1.1,"l":10,"x":"Flat overcast, warm and contrast boost"}
```

---

#### P03 — Low-Light Indoor
**Kondisi:** Dalam ruangan cahaya redup, lampu incandescent/tungsten  
**Diagnosis:** `Underexposed, warm cast, shadow detail lost`

Angkat shadow dan brightness secara bersamaan. Jaga `c >= 1.0` agar tidak flat.
Kurangi warmth karena tungsten memberikan cast terlalu kuning.

**Perhatian:**
- `d` dan `b` harus diangkat bersama — jangan hanya salah satu
- Highlight recovery `-10` mencegah window/lampu clipping
- Noise akan muncul saat shadow diangkat — pertimbangkan denoise di post

```json
{"b":25,"c":1.05,"s":0.95,"v":1.1,"h":-10,"d":35,"k":-10,"n":10,"w":-10,"t":5,"p":1.1,"l":8,"x":"Low light indoor, lift shadows, correct tungsten"}
```

---

#### P04 — Backlight/Contre-Jour
**Kondisi:** Sumber cahaya di belakang subjek, background jauh lebih terang  
**Diagnosis:** `Dark subject, bright background, high dynamic range`

Kasus paling umum yang sering salah ditangani. **JANGAN flatten contrast.**
Angkat shadow kuat, recovery highlight kuat, tapi pertahankan `c ≈ 1.0`.
Subjek harus tetap punya depth dan separation dari background.

**PARAMETER LOCK:**
- `c` harus `0.90 .. 1.05` — lebih tinggi akan membuat gambar terlihat HDR/plastik
- `d` harus `> +25` — tanpa ini subjek tetap gelap
- `h` harus `< -25` — tanpa ini background clipping

**Perhatian:**
- Jika background sangat terang (pantai, salju), naikkan `h` hingga -60
- Jika subjek masih gelap setelah `d:+45`, tambah `b` maksimal +25

```json
{"b":15,"c":0.98,"s":1.0,"v":1.1,"h":-45,"d":45,"k":-5,"n":0,"w":0,"t":0,"p":1.05,"l":5,"x":"Backlight, lift subject, protect highlights"}
```

---

#### P05 — Golden Hour
**Kondisi:** Matahari terbenam/terbit, cahaya keemasan hangat  
**Diagnosis:** `Warm golden cast, high contrast, rich saturation`

Pertahankan warmth sebagai bagian dari karakter foto.
Hanya recovery highlight jika ada clipping. Kurangi saturation ringan agar tidak terlihat plastik.

**Perhatian:**
- Ini BUKAN kasus yang perlu dikoreksi warmth-nya — warm adalah intended look
- `s:0.95` mencegah kulit terlihat oranye meski warna environment hangat

```json
{"b":-5,"c":1.1,"s":0.95,"v":1.05,"h":-20,"d":15,"k":-5,"n":0,"w":15,"t":-5,"p":1.0,"l":10,"x":"Golden hour, preserve warmth, recover highlights"}
```

---

#### P06 — High-Key Studio
**Kondisi:** Studio lighting terang merata, background putih atau abu muda  
**Diagnosis:** `Overexposed background, flat studio light`

Recovery highlight kuat untuk background. Contrast dijaga agar skin tidak flat.
Hati-hati terhadap highlight clipping di area skin yang langsung kena cahaya.

```json
{"b":-10,"c":1.1,"s":1.0,"v":1.05,"h":-30,"d":10,"k":-5,"n":5,"w":0,"t":0,"p":1.05,"l":8,"x":"High-key studio, highlight recovery, maintain contrast"}
```

---

### Kategori 2: Koreksi Warna

---

#### P07 — Blue Sky Spill
**Kondisi:** Outdoor langit biru cerah, bayangan terasa kebiruan (color spill dari langit)  
**Diagnosis:** `Blue sky color spill on shadows and skin`

Refleksi langit biru masuk ke area bayangan dan skin pada foto outdoor.
`w:+10` untuk counter blue spill. `t:+5` magenta ringan jika skin affected.

**Perhatian:**
- Ini bukan koreksi white balance global — hanya counter shadow spill
- Jangan terlalu hangat atau foto terlihat tidak natural di outdoor

```json
{"b":0,"c":1.05,"s":1.0,"v":1.1,"h":0,"d":10,"k":0,"n":0,"w":10,"t":5,"p":1.0,"l":5,"x":"Blue sky spill, warm shadows, neutral skin"}
```

---

#### P08 — Green Wall/Ceiling Spill ⚠️
**Kondisi:** Dinding/plafon hijau memantul ke skin dan subjek  
**Diagnosis:** `Green environmental spill on skin`

Kasus paling tricky dan paling umum di studio indoor.
`t:+magenta` untuk cancel spill. **JANGAN over-correct** — hanya cancel spill, jangan shift entire image.

**PARAMETER LOCK:**
- `t` harus `+10 .. +28` — lebih tinggi akan shift seluruh gambar ke magenta
- `s` harus `< 1.0` — saturation turun untuk meredam intensitas spill
- `w` hanya `+5 .. +10` — jangan lebih

**Perhatian:**
- Selalu cek skin tone setelah koreksi — kulit harus warm-neutral, bukan magenta
- Jika spill ringan, mulai dari `t:+12` dan naikkan bertahap

```json
{"b":0,"c":1.0,"s":0.92,"v":1.05,"h":0,"d":5,"k":0,"n":0,"w":7,"t":20,"p":1.0,"l":0,"x":"Green wall spill, magenta tint correction, skin safe"}
```

---

#### P09 — LED/Fluorescent Green Cast
**Kondisi:** Lampu LED atau fluorescent, seluruh gambar terlihat hijau  
**Diagnosis:** `Whole image green cast, LED/fluorescent source`

Berbeda dari Green Spill (P08) — ini seluruh gambar terkena cast, bukan hanya area bayangan.
Tint negatif (ke hijau) lebih kuat untuk counter. Warmth naik sedikit.

**Perbedaan P08 vs P09:**
- P08 (Green Spill): hanya area shadow/skin yang hijau, background bisa normal
- P09 (Green Cast): seluruh gambar uniform hijau termasuk highlight

```json
{"b":5,"c":1.05,"s":0.9,"v":1.0,"h":0,"d":10,"k":0,"n":0,"w":8,"t":-20,"p":1.0,"l":0,"x":"LED green cast, global tint and warmth correction"}
```

---

#### P10 — Neon/Mixed Artificial Light
**Kondisi:** Lingkungan neon, multiple color source, bar/club/event  
**Diagnosis:** `Complex mixed color cast, no single correction`

Kasus paling sulit. Tidak ada koreksi warna tunggal yang sempurna.
Strategi: naikkan contrast untuk dramatik, turunkan saturation agar tidak chaos,
dan biarkan warna neon sebagai karakter foto.

**Perhatian:**
- Jangan coba koreksi white balance ke neutral — itu justru merusak mood
- `k:-15` untuk mempertajam blacks yang biasanya terangkat di mixed light
- Ini adalah kasus di mana "diagnosis" lebih penting dari "koreksi"

```json
{"b":5,"c":1.2,"s":0.85,"v":1.0,"h":-10,"d":20,"k":-15,"n":0,"w":0,"t":0,"p":1.1,"l":15,"x":"Mixed neon light, mood preserve, contrast boost"}
```

---

### Kategori 3: Skin Tone

---

#### P11 — Skin Oversaturated/Orange
**Kondisi:** Kulit terlalu oranye atau merah, tidak natural  
**Diagnosis:** `Skin oversaturated, orange or red cast`

Turunkan saturation dan vibrance. Tambah sedikit coolness jika masih oranye.
Clarity negatif ringan untuk menyamarkan ketidaknaturalan.

**BATAS SKIN TONE (wajib dipatuhi):**
- `v` maksimal `1.3` — di atas ini skin terlihat plastik
- `s` maksimal `1.2` — di atas ini kulit terlihat seperti sunburn

```json
{"b":0,"c":1.0,"s":0.88,"v":0.95,"h":-5,"d":0,"k":0,"n":0,"w":-5,"t":8,"p":1.0,"l":-5,"x":"Skin oversaturated, reduce sat and warmth"}
```

---

#### P12 — Skin Pale/Cold
**Kondisi:** Kulit terlihat pucat, kebiruan, atau abu-abu  
**Diagnosis:** `Skin undersaturated, cool or gray tone`

Warmth naik untuk memberikan kehangatan ke skin.
Vibrance lebih aman dari saturation — tidak over-saturate area non-skin.

```json
{"b":5,"c":1.05,"s":1.05,"v":1.2,"h":0,"d":5,"k":0,"n":0,"w":15,"t":-5,"p":1.0,"l":0,"x":"Pale skin, boost warmth and vibrance gently"}
```

---

#### P13 — Portrait Skin Soften
**Kondisi:** Portrait wajah close-up, ingin skin halus dan flattering  
**Diagnosis:** `Portrait requiring soft skin rendering`

Clarity negatif adalah fitur utama preset ini — ini yang membuat skin terlihat halus.
Kurangi sharpness ringan. Jangan terlalu banyak — akan terlihat plastik atau blur.

**Perhatian:**
- Ini hanya untuk portrait — jangan gunakan di foto landscape/produk
- `l:-12` adalah titik manis; lebih dari `-15` mulai terlihat buatan

```json
{"b":5,"c":1.0,"s":1.0,"v":1.15,"h":0,"d":8,"k":0,"n":5,"w":5,"t":0,"p":0.85,"l":-12,"x":"Portrait soft skin, negative clarity, vibrance boost"}
```

---

### Kategori 4: Lingkungan

---

#### P14 — Indoor Window Light
**Kondisi:** Cahaya dari jendela satu arah, bayangan satu sisi  
**Diagnosis:** `Directional natural light, mild cool cast`

Cahaya jendela biasanya agak dingin dan satu arah. Bayangan satu sisi perlu shadow lift ringan.
Warmth naik sedikit untuk counter color temperature jendela.

```json
{"b":5,"c":1.1,"s":1.05,"v":1.1,"h":0,"d":20,"k":0,"n":0,"w":8,"t":0,"p":1.0,"l":8,"x":"Window light, lift directional shadows, warm slightly"}
```

---

#### P15 — Malam/Night Photography
**Kondisi:** Foto malam, campuran sumber cahaya artifisial di outdoor  
**Diagnosis:** `Low light, mixed sources, visible noise`

Angkat shadow hati-hati — terlalu banyak akan memunculkan noise.
Contrast tinggi untuk menjaga moodiness. `k:-20` untuk blacks yang dalam.

**Perhatian:**
- `d` jangan lebih dari +30 jika ada area hitam pekat (langit malam)
- `p:0.9` karena sharpness tinggi akan memperparah noise

```json
{"b":20,"c":1.15,"s":0.9,"v":1.05,"h":-15,"d":25,"k":-20,"n":15,"w":0,"t":0,"p":0.9,"l":5,"x":"Night photo, preserve mood, careful shadow lift"}
```

---

#### P16 — Hazy/Foggy Outdoor
**Kondisi:** Kabut atau haze di outdoor, warna flat dan pucat  
**Diagnosis:** `Haze/fog, low saturation and contrast`

Haze menyebabkan blacks terangkat dan saturation drop.
Turunkan blacks agresif, naikkan contrast dan saturation lebih dari biasanya.

```json
{"b":0,"c":1.2,"s":1.2,"v":1.2,"h":0,"d":0,"k":-25,"n":10,"w":5,"t":0,"p":1.1,"l":20,"x":"Haze/fog, deep blacks, contrast and saturation boost"}
```

---

## Perbaikan System Prompt

### Problem: LLM Tidak Konsisten

Penyebab utama inkonsistensi:
1. Model "menebak" kondisi tanpa struktur deteksi yang jelas
2. Tidak ada parameter lock per kondisi — nilai bisa melayang ke mana saja
3. Tidak ada referensi baseline yang konkret

### Solusi 1: Detection Checklist

Tambahkan di awal system prompt sebelum workflow:

```
DETECTION CHECKLIST (evaluate these IN ORDER before setting any parameter):
A) EXPOSURE: Is overall scene dark / normal / bright?
   dark → b must be +15 or more, d must be +20 or more
   bright/blown → h must be -20 or less

B) COLOR CAST: Is there a dominant cast?
   warm/yellow → w negative (-5 to -15)
   cool/blue → w positive (+5 to +15)
   green (global) → t negative (-15 to -25)
   green (spill on skin only) → t positive (+10 to +25)

C) SKIN VISIBLE: Does skin look orange / pale / green?
   orange → s 0.85..0.95, v 0.9..1.0
   pale → w +10 to +15, v 1.1 to 1.2
   green-tinted → t +15 to +25

D) BACKLIGHT: Is background clearly brighter than subject?
   YES → d must be +30 or more, h must be -30 or less, c must be 0.90..1.05

E) PRESET CLASS: Based on A-D, classify as one of:
   DAYLIGHT | OVERCAST | LOWLIGHT | BACKLIGHT | GREEN_SPILL | GREEN_CAST |
   GOLDEN_HR | HIGH_KEY | NEON | PORTRAIT | NIGHT | HAZE
   Then apply the corresponding preset as base, fine-tune as needed.
```

### Solusi 2: Parameter Locks Per Kondisi

Tambahkan di bagian SPECIAL CASES:

```
PARAMETER LOCKS (these ranges are non-negotiable per condition):
- BACKLIGHT: c=0.90..1.05, d>=+30, h<=-25
- GREEN_SPILL: t=+10..+28, s<=0.95
- LOWLIGHT: b>=+15, d>=+20, c>=1.0
- PORTRAIT (soft): l=-8..-15, p=0.8..0.95, v<=1.2
- SKIN any condition: v<=1.3, s<=1.2
```

### Solusi 3: Two-Pass Pipeline (Rekomendasi Utama)

Pisahkan diagnosis dari koreksi untuk konsistensi maksimal:

**Pass 1 — Klasifikasi kondisi:**
```python
CLASSIFY_PROMPT = """
Analyze this photo and output ONLY ONE of these condition codes, nothing else:
DAYLIGHT | OVERCAST | LOWLIGHT | BACKLIGHT | GREEN_SPILL | GREEN_CAST |
GOLDEN_HR | HIGH_KEY | NEON | PORTRAIT | NIGHT | HAZE | SKIN_WARM | SKIN_PALE
"""
```

**Pass 2 — Koreksi parameter:**
```python
# Setelah dapat kondisi, load preset baseline lalu kirim ke LLM:
CORRECT_PROMPT = f"""
Photo condition detected: {condition}
Base preset: {json.dumps(PRESETS[condition])}
Fine-tune the parameters based on the actual image. Adjust only what differs from the base.
Return ONLY the adjusted JSON, same format as base preset.
"""
```

Pendekatan ini meningkatkan konsistensi secara dramatis karena setiap call punya scope yang sempit.

---

## Preset JSON Library Lengkap

Lihat file `presets.json` untuk semua preset dalam format siap-pakai.

---

## Catatan Implementasi OpenCV

Parameter mapping ke OpenCV:

```python
def apply_params(img, p):
    # b: brightness → addWeighted atau direct add
    # c: contrast → multiplicative (img * c, lalu clip)
    # s/v: saturation/vibrance → convert ke HSV, adjust S channel
    # h/d: highlights/shadows → tone curve atau masking berdasarkan luminance
    # k/n: blacks/whites → levels adjustment (input/output range)
    # w: warmth → adjust R dan B channel (warm: +R, -B)
    # t: tint → adjust G channel (positive: +R+B aka magenta, negative: +G)
    # p: sharpness → cv2.filter2D unsharp mask
    # l: clarity → midtone contrast via sigmoid atau local contrast
    pass
```

---

*Riset ini dibuat untuk pipeline auto-colorize dengan LLM + OpenCV.*
*Versi: 1.0 | Parameter berdasarkan analisis Lightroom-equivalent corrections*
