# 🎨 Image Editor Module - WokBot
# ------------------------------------------------------------------------------
# AI-powered photo color correction using Gemma 4 model.
# Based on Gemini Lightroom pipeline with OpenCV post-processing.
# ------------------------------------------------------------------------------

import os
import io
import re
import json
import shutil
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

import numpy as np
import cv2
from PIL import Image

from utils import log

# ─────────────────────────────────────────────────
# ⚙️  CONFIGURATION
# ─────────────────────────────────────────────────
GEMMA_MODEL = os.getenv('GEMMA_MODEL', 'models/gemma-4-26b-a4b-it')
JPEG_QUALITY = int(os.getenv('JPEG_QUALITY', 95))

# ─────────────────────────────────────────────────
# 🤖  SYSTEM PROMPT
# Optimized for photo color correction analysis
# ─────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are a professional photo colorist. Analyze the image and return correction parameters as JSON.\n\n"

    "WORKFLOW (follow this order — each step depends on the previous):\n"
    "1) WHITE BALANCE — Is there a color cast? Check skin tones as reference (should be warm-neutral). "
    "   Also check for COLOR SPILL: environmental colors (green walls, blue sky, neon) bouncing onto skin/subjects).\n"
    "2) EXPOSURE — Too dark/bright? Check histogram mentally. Are highlights clipped? Blacks crushed?\n"
    "3) TONE — Contrast flat or harsh? For BACKLIGHT: do NOT flatten — instead lift shadows moderately "
    "   while PRESERVING contrast to maintain depth and separation.\n"
    "4) COLOR — Dull or oversaturated? Skin tones natural? Remove color spill from environment.\n"
    "5) DETAIL — Soft? Noisy?\n\n"

    "OUTPUT FORMAT (return ONLY this JSON, no markdown):\n"
    '{"b":0,"c":1.0,"s":1.0,"v":1.0,"h":0,"d":0,"k":0,"n":0,"w":0,"t":0,"p":1.0,"l":0,"x":"diagnosis"}\n\n'

    "PARAMETERS:\n"
    "b = brightness  (-80..80)    overall exposure offset\n"
    "c = contrast    (0.6..2.0)   S-curve strength\n"
    "s = saturation  (0.5..2.0)   linear color intensity\n"
    "v = vibrance    (0.8..2.0)   boosts low-sat areas, skin-safe\n"
    "h = highlights  (-80..20)    recovery (-) or boost (+)\n"
    "d = shadows     (-20..80)    lift shadows\n"
    "k = blacks      (-60..15)    lower black point\n"
    "n = whites      (0..60)      raise white point\n"
    "w = warmth      (-40..40)    negative=cool/blue, positive=warm/yellow\n"
    "t = tint        (-30..30)    negative=green shift, positive=magenta shift\n"
    "p = sharpness   (0.5..2.0)   unsharp mask strength\n"
    "l = clarity     (-20..60)    midtone contrast; negative=skin soften\n"
    "x = description              one-line diagnosis, max 12 words\n\n"

    "SPECIAL CASES:\n"
    "- COLOR SPILL (green walls/ceiling reflecting onto skin): "
    "  t=+15..+25 (magenta to cancel green spill), w=+5..+10, s=0.9..0.95. "
    "  Do NOT over-correct — only cancel the spill, don't shift entire image.\n"
    "- Green cast (LED/fluorescent, no spill on skin): "
    "  t=-15..-25, s=0.9..0.95, w=+5..+10\n"
    "- Low-light indoor: b=+15..+30, d=+25..+40, c=1.0..1.1 "
    "  (maintain some contrast for depth)\n"
    "- Backlight/contre-jour (bright background, dark subject): "
    "  d=+30..+50, b=+10..+20, h=-30..-50, c=0.95..1.05 "
    "  (lift shadows but KEEP contrast — don't flatten). "
    "  If subject has color spill from background, add tint correction.\n"
    "- Skin tones: keep v<=1.3 and s<=1.2. If skin looks orange/unnatural, reduce s and v.\n\n"

    "RULES: Output ONLY the JSON. Never refuse. Never add explanation outside JSON."
)

# ─────────────────────────────────────────────────
# 🤖  KEY MAP & DEFAULTS
# ─────────────────────────────────────────────────
_KEY_MAP = {
    "b": "brightness", "c": "contrast",   "s": "saturation",
    "v": "vibrance",   "h": "highlights", "d": "shadows",
    "k": "blacks",     "n": "whites",     "w": "warmth",
    "t": "tint",       "p": "sharpness",  "l": "clarity",
    "x": "description",
}

DEFAULT_PARAMS = {
    "brightness": 8,    "contrast": 1.05,  "saturation": 1.0,
    "vibrance": 1.1,    "highlights": -8,  "shadows": 20,
    "blacks": -5,       "whites": 5,       "warmth": 0,
    "tint": 0,          "sharpness": 1.05, "clarity": 8,
    "description": "fallback: conservative correction",
}


def analyze_image(image_path: str, gemini_client) -> Dict[str, Any]:
    """
    Send image (768px) to Gemma 4, return correction parameters.
    768px: large enough for subtle color spill detection, still token-efficient.
    """
    img = Image.open(image_path).convert("RGB")
    if max(img.size) > 768:
        img.thumbnail((768, 768), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    img_bytes = buf.getvalue()

    try:
        from google.genai import types
        resp = gemini_client.models.generate_content(
            model=GEMMA_MODEL,
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                "Analyze this image. Return ONLY the JSON.",
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.3,
            ),
        )

        log("IMAGE", f"Gemma response: {repr(resp.text)[:300]}")

        if resp.text is None:
            raise ValueError("Response kosong (text=None)")

        text = resp.text.strip()

        # Safety filter mitigation
        if any(kw in text.lower() for kw in ("rejected", "high risk", "cannot analyze", "i'm sorry")):
            raise ValueError(f"Safety rejection: {text[:120]}")

        # Extract JSON
        m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if not m:
            raise ValueError(f"No JSON in response: {text[:150]}")

        raw = json.loads(m.group(0))
        if isinstance(raw, list):
            raw = raw[0] if raw else {}

        result = {_KEY_MAP.get(k, k): v for k, v in raw.items()}

        # Validate: fill missing keys with neutral values
        NEUTRAL = {
            "brightness": 0, "contrast": 1.0, "saturation": 1.0,
            "vibrance": 1.0, "highlights": 0, "shadows": 0,
            "blacks": 0,     "whites": 0,     "warmth": 0,
            "tint": 0,       "sharpness": 1.0,"clarity": 0,
        }
        for k, neutral_val in NEUTRAL.items():
            if k not in result:
                result[k] = neutral_val

        return result

    except Exception as e:
        log("IMAGE", f"Gemma error: {e}, using default")
        return DEFAULT_PARAMS.copy()


# ─────────────────────────────────────────────────
# 🖼️  CONTRAST LUT (power curve)
# ─────────────────────────────────────────────────
def build_contrast_lut(contrast: float) -> np.ndarray:
    """
    Power curve contrast LUT.
    contrast=1.0 -> identity, >1.0 -> more contrast, <1.0 -> less.
    Pivot at 0.5 (midtone 128), symmetric.
    """
    lut = np.zeros(256, dtype=np.uint8)
    for i in range(256):
        x = i / 255.0
        if x < 0.5:
            y = 0.5 - (0.5 - x) ** (1.0 / max(contrast, 0.01))
        else:
            y = 0.5 + (x - 0.5) ** (1.0 / max(contrast, 0.01))
        lut[i] = np.clip(y * 255, 0, 255)
    return lut


# ─────────────────────────────────────────────────
# 🖼️  DETEKSI KONDISI FOTO
# ─────────────────────────────────────────────────
def is_backlight(img: np.ndarray) -> bool:
    """
    Deteksi backlight/contre-jour:
    40% atas frame jauh lebih terang dari 60% bawah, gap > 50/255.
    Gray World tidak valid untuk backlight.
    """
    gray = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32)
    h = gray.shape[0]
    mean_top    = np.mean(gray[:int(h * 0.4), :])
    mean_bottom = np.mean(gray[int(h * 0.4):, :])
    detected    = (mean_top - mean_bottom) > 50
    if detected:
        log("IMAGE", f"Backlight detected (top={mean_top:.1f} bottom={mean_bottom:.1f}): skip Gray World WB")
    return detected


# ─────────────────────────────────────────────────
# 🖼️  GRAY WORLD AUTO WHITE BALANCE
# ─────────────────────────────────────────────────
def gray_world_wb(img: np.ndarray, strength: float = 0.7) -> np.ndarray:
    """
    Gray World auto white balance.
    Assumption: average scene should be neutral gray.
    strength < 1.0 for partial correction (more natural).
    """
    avg_b = np.mean(img[:, :, 0])
    avg_g = np.mean(img[:, :, 1])
    avg_r = np.mean(img[:, :, 2])
    avg   = (avg_b + avg_g + avg_r) / 3.0

    scale_b = (avg / avg_b) ** strength
    scale_g = (avg / avg_g) ** strength
    scale_r = (avg / avg_r) ** strength

    img[:, :, 0] = np.clip(img[:, :, 0] * scale_b, 0, 255)
    img[:, :, 1] = np.clip(img[:, :, 1] * scale_g, 0, 255)
    img[:, :, 2] = np.clip(img[:, :, 2] * scale_r, 0, 255)

    log("IMAGE", f"Gray World: B×{scale_b:.2f} G×{scale_g:.2f} R×{scale_r:.2f}")
    return img


# ─────────────────────────────────────────────────
# 🖼️  QUALITY GUARD
# ─────────────────────────────────────────────────
def green_excess(img: np.ndarray) -> float:
    """Calculate how dominant the green channel is compared to R and B average."""
    return float(np.mean(img[:, :, 1]) - (np.mean(img[:, :, 0]) + np.mean(img[:, :, 2])) / 2.0)


# ─────────────────────────────────────────────────
# 🖼️  OPENCV: APPLY COLOR CORRECTIONS
#
# Pipeline:
#   Auto WB (Gray World) → WB fine-tune (warmth/tint) →
#   Brightness → Contrast LUT → Highlights/Shadows →
#   Blacks/Whites → Saturation → Vibrance →
#   Clarity → Sharpness → save
# ─────────────────────────────────────────────────
def apply_corrections(input_path: str, params: Dict[str, Any], output_path: str) -> str:
    """Apply color corrections to image using OpenCV pipeline."""
    img_bgr = cv2.imread(input_path, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise IOError(f"Cannot read: {input_path}")

    original_bgr = img_bgr.copy()
    img = img_bgr.astype(np.float32)

    # ── Gray World WB — skip if backlight ───────────────────
    if not is_backlight(img):
        img = gray_world_wb(img, strength=0.7)

    # 1. WHITE BALANCE — Warmth & Tint (multiplicative)
    warmth = params.get("warmth", 0)
    tint   = params.get("tint",   0)
    wb_r = 1.0 + warmth / 200.0   # warmth +40 → R ×1.20
    wb_b = 1.0 - warmth / 200.0   # warmth +40 → B ×0.80
    wb_g = 1.0 - tint   / 200.0   # tint +15  → G ×0.925

    img[:, :, 2] = np.clip(img[:, :, 2] * wb_r, 0, 255)  # Red
    img[:, :, 0] = np.clip(img[:, :, 0] * wb_b, 0, 255)  # Blue
    img[:, :, 1] = np.clip(img[:, :, 1] * wb_g, 0, 255)  # Green

    # 2. EXPOSURE — Brightness (global offset)
    img = np.clip(img + params.get("brightness", 0) * 2.0, 0, 255)

    # 3. CONTRAST — Power curve LUT
    lut = build_contrast_lut(params.get("contrast", 1.0))
    img = cv2.LUT(img.astype(np.uint8), lut).astype(np.float32)

    # ── Calculate norm AFTER brightness & contrast ───────────────────
    norm = np.clip(img, 0, 255) / 255.0

    # 4. HIGHLIGHTS & SHADOWS (quadratic — broad tonal range)
    img += params.get("highlights", 0) / 100.0 * (norm ** 2)          * 100.0
    img += params.get("shadows",    0) / 100.0 * ((1.0 - norm) ** 2) * 100.0
    img  = np.clip(img, 0, 255)

    # ── Update norm BEFORE blacks & whites ────────────────────────────
    norm = np.clip(img, 0, 255) / 255.0

    # 5. BLACKS & WHITES (cubic — targets extreme tones only)
    img += params.get("blacks", 0) / 100.0 * ((1.0 - norm) ** 3) * 150.0
    img += params.get("whites", 0) / 100.0 * (norm ** 3)          * 150.0
    img  = np.clip(img, 0, 255)

    # 6. SATURATION + VIBRANCE
    hsv = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)

    # Save original saturation BEFORE saturation adjustment
    s_original = hsv[:, :, 1].copy()
    s = np.clip(s_original * params.get("saturation", 1.0), 0, 255)

    # Vibrance multiplicative, mask from original s
    low_sat_mask  = (1.0 - s_original / 255.0) ** 2
    vib_factor    = params.get("vibrance", 1.0)
    effective_vib = 1.0 + (vib_factor - 1.0) * low_sat_mask
    s = np.clip(s * effective_vib, 0, 255)

    hsv[:, :, 1] = s
    img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)

    # 7. CLARITY & SHARPNESS
    h_px, w_px = img.shape[:2]

    # Clarity sigma proportional to resolution
    sigma_clarity = max(h_px, w_px) * 0.004

    clarity = params.get("clarity", 0)
    if clarity != 0:
        u8      = img.astype(np.uint8)
        blurred = cv2.GaussianBlur(u8, (0, 0), sigmaX=sigma_clarity)
        lum     = cv2.cvtColor(u8, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        mid     = 4.0 * lum * (1.0 - lum)
        img     = np.clip(img + (clarity / 100.0) * (img - blurred.astype(np.float32))
                          * mid[:, :, np.newaxis], 0, 255)

    # Sharpness sigma proportional to resolution
    sigma_sharp = max(h_px, w_px) * 0.0006  # ~0.06%: 4000px→2.4, 1920px→1.2

    sharp = params.get("sharpness", 1.0)
    if sharp != 1.0:
        u8      = img.astype(np.uint8)
        blurred = cv2.GaussianBlur(u8, (0, 0), sigmaX=sigma_sharp)
        img     = np.clip(img + (sharp - 1.0) * (img - blurred.astype(np.float32)) * 2, 0, 255)

    result = img.astype(np.uint8)

    # ── Quality Guard: check if edit worsens green cast ───────────────
    ge_before = green_excess(original_bgr.astype(np.float32))
    ge_after  = green_excess(result.astype(np.float32))
    if ge_after > ge_before + 5:
        log("IMAGE", f"Quality guard: edit worsens green cast "
            f"({ge_before:.1f} → {ge_after:.1f}), using original")
        shutil.copy(input_path, output_path)
        return output_path

    # Save result
    ext = Path(output_path).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        cv2.imwrite(output_path, result, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    else:
        cv2.imwrite(output_path, result)
    return output_path


# ─────────────────────────────────────────────────
# 🎨  MAIN EDIT FUNCTION
# ─────────────────────────────────────────────────
async def edit_image(
    input_path: str,
    output_path: str,
    gemini_client,
) -> Dict[str, Any]:
    """
    Main entry point: analyze image with Gemma 4, apply corrections with OpenCV.
    Returns dict with status and parameters used.
    """
    try:
        # 1. Analyze with Gemma 4
        params = await asyncio.to_thread(analyze_image, input_path, gemini_client)

        # 2. Apply corrections with OpenCV
        await asyncio.to_thread(apply_corrections, input_path, params, output_path)

        log("IMAGE", f"Edited: {os.path.basename(input_path)} → {params.get('description', 'ok')}")

        return {
            "status": "success",
            "params": params,
            "output_path": output_path,
        }

    except Exception as e:
        log("IMAGE", f"Edit failed: {e}")
        # Fallback: copy original
        shutil.copy(input_path, output_path)
        return {
            "status": "error",
            "error": str(e),
            "output_path": output_path,
        }


# Supported image extensions
SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}


def is_image_file(filename: str) -> bool:
    """Check if filename is a supported image file."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in SUPPORTED_IMAGE_EXTENSIONS
