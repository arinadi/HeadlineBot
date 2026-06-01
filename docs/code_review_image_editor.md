# Code Review — `image_editor.py`

Pipeline: Gemma 4 analysis → OpenCV correction untuk auto photo colorization.

---

## Ringkasan

| Severity    | Jumlah | Dampak |
|-------------|--------|--------|
| Critical    | 3      | Output salah / koreksi bertentangan satu sama lain |
| Warning     | 4      | Hasil tidak optimal, perilaku tidak sesuai ekspektasi |
| Improvement | 3      | Konsistensi dan ketepatan lebih baik |
| Good        | 4      | Sudah benar, tidak perlu diubah |

---

## Critical Bugs

### BUG-01 — Gray World WB bertentangan dengan koreksi warmth/tint dari LLM

**Lokasi:** `apply_corrections()` — blok Gray World sebelum warmth/tint

**Masalah:**
Gray World otomatis menggeser channel R/G/B berdasarkan asumsi "scene average = neutral gray".
Namun LLM (Gemma) sudah menganalisa foto dan menghasilkan nilai `warmth` dan `tint` yang spesifik.
Kedua koreksi ini diaplikasikan secara berurutan, artinya keduanya saling berinteraksi dan bisa bertentangan.

Contoh konkret: Foto dengan green wall spill. LLM menghasilkan `t:+20` (magenta untuk cancel green).
Gray World sebelumnya sudah menggeser G-channel turun karena average G tinggi. LLM tidak "tahu"
bahwa Gray World sudah berjalan. Hasilnya: double-koreksi atau under-koreksi bergantung magnitude.

**Kode sekarang:**
```python
if not is_backlight(img):
    img = gray_world_wb(img, strength=0.7)  # selalu jalan jika bukan backlight
# lalu:
wb_g = 1.0 - tint / 200.0
img[:, :, 1] = np.clip(img[:, :, 1] * wb_g, 0, 255)  # ditumpuk di atas GW
```

**Fix — skip GW jika LLM sudah mendeteksi cast spesifik:**
```python
has_cast = abs(params.get("warmth", 0)) > 8 or abs(params.get("tint", 0)) > 8

if not is_backlight(img) and not has_cast:
    img = gray_world_wb(img, strength=0.5)  # hanya jika LLM tidak mendeteksi cast
elif not is_backlight(img):
    # Gray World dengan strength sangat rendah sebagai pre-normalization ringan
    img = gray_world_wb(img, strength=0.2)
```

Atau, opsi lebih bersih: nonaktifkan Gray World sama sekali dan biarkan LLM yang handle semua WB.
Gray World hanya berguna sebagai safety net untuk foto yang tidak memiliki cast terdeteksi LLM.

---

### BUG-02 — `is_backlight()` memberikan false positive tinggi

**Lokasi:** `is_backlight()` — deteksi hanya berdasarkan top 40% vs bottom 60%

**Masalah:**
Logika ini akan trigger backlight detection untuk:
- Semua foto outdoor dengan langit biru/putih di atas frame
- Portrait di depan jendela (sangat umum)
- Foto dari dalam mobil/ruangan ke luar

Akibatnya Gray World WB di-skip pada kasus-kasus ini, padahal sebenarnya foto tersebut
bukan backlight sejati — subjek tidak gelap, hanya background lebih terang dari rata-rata.
Ini menyebabkan color cast tidak terkoreksi di ribuan foto normal.

**Kode sekarang:**
```python
mean_top    = np.mean(gray[:int(h * 0.4), :])
mean_bottom = np.mean(gray[int(h * 0.4):, :])
detected    = (mean_top - mean_bottom) > 50
```

**Fix — cek bahwa subjek (center frame) harus gelap dibanding pinggir:**
```python
def is_backlight(img: np.ndarray) -> bool:
    gray = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = gray.shape

    # Subjek biasanya di tengah frame
    center = gray[int(h*0.25):int(h*0.75), int(w*0.25):int(w*0.75)]
    # Background: area pinggir atas dan bawah
    bg_top = gray[:int(h*0.15), :]
    bg_bot = gray[int(h*0.85):, :]
    edges  = np.concatenate([bg_top.ravel(), bg_bot.ravel()])

    mean_center = np.mean(center)
    mean_edges  = np.mean(edges)

    # Backlight: center gelap (<100), edges jauh lebih terang, gap besar
    detected = (mean_edges - mean_center) > 60 and mean_center < 120
    if detected:
        log("IMAGE", f"Backlight: center={mean_center:.1f} edges={mean_edges:.1f}")
    return detected
```

---

### BUG-03 — Highlights/Shadows mask menggunakan `norm` yang sudah ter-shift

**Lokasi:** `apply_corrections()` — kalkulasi `norm` untuk highlights/shadows

**Masalah:**
`norm` dihitung SETELAH brightness offset dan contrast LUT diaplikasikan.
Untuk foto backlight dengan `brightness: +15` dan `contrast: 0.98`, seluruh tonal distribution
sudah bergeser saat highlights dan shadows diaplikasikan. Mask `(norm**2)` untuk highlight recovery
tidak lagi menarget highlight asli foto — melainkan highlight dari gambar yang sudah ter-modifikasi.

Dampak paling terasa di foto backlight: shadow mask `(1-norm)**2` tidak lagi kuat di area
yang seharusnya — karena shadows sudah sedikit terangkat oleh brightness offset.

**Kode sekarang:**
```python
img = np.clip(img + brightness * 2.0, 0, 255)           # shift brightness
lut = build_contrast_lut(contrast)
img = cv2.LUT(img.astype(np.uint8), lut).astype(np.float32)  # apply contrast
norm = np.clip(img, 0, 255) / 255.0                      # ← dari gambar SUDAH dimodifikasi
img += highlights / 100.0 * (norm ** 2) * 100.0         # mask tidak akurat
```

**Fix — simpan norm original sebelum brightness/contrast:**
```python
# Simpan norm SEBELUM brightness dan contrast
norm_original = np.clip(img.copy(), 0, 255) / 255.0

img = np.clip(img + brightness * 2.0, 0, 255)
lut = build_contrast_lut(contrast)
img = cv2.LUT(img.astype(np.uint8), lut).astype(np.float32)

# Gunakan norm_original untuk mask tonality yang akurat
img += highlights / 100.0 * (norm_original ** 2)          * 100.0
img += shadows    / 100.0 * ((1.0 - norm_original) ** 2) * 100.0
img  = np.clip(img, 0, 255)

# Juga untuk blacks & whites:
img += blacks / 100.0 * ((1.0 - norm_original) ** 3) * 150.0
img += whites / 100.0 * (norm_original ** 3)          * 150.0
```

---

## Warnings

### WARN-01 — `DEFAULT_PARAMS` tidak benar-benar neutral

**Lokasi:** `DEFAULT_PARAMS` konstanta

**Masalah:**
Saat Gemma gagal (error, safety reject, timeout), `DEFAULT_PARAMS` diterapkan ke foto.
Nilai sekarang: `brightness:8, shadows:20, clarity:8` — ini bukan fallback neutral,
ini adalah "conservative correction" yang di-apply ke SEMUA foto yang gagal dianalisa.
Foto outdoor siang hari yang sudah well-exposed akan jadi over-bright.

**Fix:**
```python
DEFAULT_PARAMS = {
    "brightness": 0,  "contrast": 1.0,  "saturation": 1.0,
    "vibrance": 1.0,  "highlights": 0,  "shadows": 0,
    "blacks": 0,      "whites": 0,      "warmth": 0,
    "tint": 0,        "sharpness": 1.0, "clarity": 0,
    "description": "fallback: no correction (analysis failed)",
}
```

Jika ingin ada "gentle" default yang lebih baik dari foto mentah, pertimbangkan preset `DAYLIGHT`
dari `presets.json` sebagai fallback — tapi hanya setelah ada confidence bahwa kondisi foto memang normal.

---

### WARN-02 — `build_contrast_lut()` menggunakan power curve, bukan S-curve

**Lokasi:** `build_contrast_lut()`

**Masalah:**
Power curve `y = 0.5 ± (0.5 - x)^(1/c)` tidak identik dengan S-curve Lightroom.
Pada contrast tinggi (c > 1.4), power curve mendorong shadow/highlight ke ekstrem terlalu agresif
tanpa soft shoulder yang melindungi detail di area gelap/terang. Hasilnya: shadow bisa crush,
highlight bisa clip — padahal ada nilai `h` dan `k` untuk kontrolnya.

**Improvement — S-curve dengan soft shoulder:**
```python
def build_contrast_lut(contrast: float) -> np.ndarray:
    x = np.arange(256, dtype=np.float32) / 255.0
    if abs(contrast - 1.0) < 0.01:
        return x_to_lut(x)  # identity
    k = (contrast - 1.0) * 4.0
    # tanh-based S-curve: smooth shoulder di shadow dan highlight
    denom = 2.0 * np.tanh(k * 0.5) + 1e-6
    y = 0.5 + np.tanh(k * (x - 0.5)) / denom
    return np.clip(y * 255, 0, 255).astype(np.uint8)

def x_to_lut(x):
    return np.clip(x * 255, 0, 255).astype(np.uint8)
```

---

### WARN-03 — Quality guard hanya cek green excess

**Lokasi:** `green_excess()` dan blok quality guard di akhir `apply_corrections()`

**Masalah:**
Guard ini hanya melindungi dari memperburuk green cast. Tidak ada proteksi dari:
- Over-brightening (terlalu banyak pixel clipping di putih)
- Extreme color shift ke warna lain karena warmth/tint yang ekstrem dari LLM
- Contrast yang terlalu agresif menghasilkan crushed blacks

**Fix — guard yang lebih komprehensif:**
```python
def quality_guard(original: np.ndarray, result: np.ndarray) -> bool:
    """Return True jika edit memperburuk foto secara signifikan."""
    # Cek highlight clipping
    clip_before = np.mean(original > 250)
    clip_after  = np.mean(result  > 250)
    if clip_after > clip_before + 0.05:  # >5% lebih pixel clipping
        log("IMAGE", f"Quality guard: clip worse ({clip_before:.3f} → {clip_after:.3f})")
        return True

    # Cek green cast
    ge_before = green_excess(original.astype(np.float32))
    ge_after  = green_excess(result.astype(np.float32))
    if ge_after > ge_before + 5:
        log("IMAGE", f"Quality guard: green worse ({ge_before:.1f} → {ge_after:.1f})")
        return True

    return False
```

---

### WARN-04 — Divisor warmth/tint (200.0) menghasilkan efek terlalu lemah

**Lokasi:** `apply_corrections()` — `wb_r = 1.0 + warmth / 200.0`

**Masalah:**
Warmth range adalah -40..40. Dengan divisor 200, warmth maksimum +40 menghasilkan
`R × 1.20` — ini lemah untuk kasus green spill yang kuat. LLM mungkin menghasilkan
`t:+20` untuk cancel green spill, tapi efek aktualnya hanya `G × 0.90`, sementara
spill yang kuat membutuhkan koreksi lebih besar.

Perbandingan range efektif:
- warmth +40 → R × 1.20, B × 0.80 (divisor 200) — lemah
- warmth +40 → R × 1.27, B × 0.73 (divisor 150) — lebih terasa

**Fix:**
```python
wb_r = 1.0 + warmth / 150.0   # warmth +40 → R × 1.267
wb_b = 1.0 - warmth / 150.0
wb_g = 1.0 - tint   / 150.0   # tint +25 → G × 0.833 (lebih efektif cancel green)
```

Catatan: jika mengubah ini, perlu re-kalibrasi nilai preset di `presets.json` karena
nilai `w` dan `t` yang sama akan menghasilkan efek berbeda.

---

## Improvements

### INFO-01 — Temperature LLM bisa diturunkan untuk konsistensi JSON

**Lokasi:** `analyze_image()` — `temperature=0.3`

Untuk tugas structured output (JSON numerik), `temperature=0.1` lebih deterministic.
Ini langsung mengurangi inkonsistensi nilai antar foto yang mirip kondisinya.

```python
config=types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    temperature=0.1,
)
```

---

### INFO-02 — Pertimbangkan two-pass pipeline untuk konsistensi maksimal

Lihat `photo_colorize_presets_research.md` bagian "Solusi 3: Two-Pass Pipeline".
Pass 1 hanya menghasilkan satu kata kondisi (`BACKLIGHT`, `GREEN_SPILL`, dll.).
Pass 2 menerima preset baseline + gambar dan fine-tune parameter.

Scope yang lebih sempit per call → output jauh lebih konsisten.

---

### INFO-03 — `analyze_image()` bisa langsung async jika client mendukung

```python
# Jika google.genai client mendukung async:
async def analyze_image(image_path, gemini_client):
    resp = await gemini_client.models.generate_content_async(...)
    # tanpa asyncio.to_thread overhead
```

---

## Good Practice — Sudah Benar, Jangan Diubah

**Backlight skip Gray World** — konsep benar, Gray World tidak valid untuk intentional asymmetry.
Hanya perbaiki detection accuracy-nya (BUG-02).

**Sigma clarity/sharpness proporsional resolusi** — `sigma = max(h,w) * 0.004` sudah scale-aware.
Tidak hardcoded pixel — akan bekerja konsisten di berbagai resolusi input.

**Vibrance mask dari `s_original`** — menggunakan saturasi sebelum adjustment sebagai mask sudah tepat.
Ini memastikan vibrance boost tidak over-saturate area yang sudah saturated.

**Clarity luminance mask** — `mid = 4.0 * lum * (1.0 - lum)` adalah implementasi yang benar.
Nilai mendekati 0 di shadow/highlight, puncak di midtone (~0.5). Melindungi dari halos.

**JSON regex fallback** — `re.search(r"\{[^{}]*\}", text)` sudah menangani kasus model
menambahkan penjelasan di luar JSON. Robust untuk Gemma yang terkadang verbose.

---

## Urutan Fix yang Disarankan

1. **BUG-03** — norm_original (paling mudah, dampak langsung ke akurasi tonal)
2. **WARN-01** — DEFAULT_PARAMS neutral (penting untuk foto well-exposed)
3. **BUG-01** — GW skip logic berdasarkan cast LLM
4. **BUG-02** — is_backlight() dengan center detection
5. **WARN-04** — divisor 150 untuk warmth/tint (lakukan bersamaan dengan re-kalibrasi preset)
6. **WARN-03** — quality guard komprehensif
7. **INFO-01** — temperature 0.1

---

*Review ini mencakup `image_editor.py` versi yang diberikan.*
*Referensi preset: `presets.json` dan `photo_colorize_presets_research.md`*
