# 🎨 Image Editor Module - HeadlineBot
# ------------------------------------------------------------------------------
# AI-powered photo color correction using Gemma 4 model.
# Two-pass pipeline: classify condition → apply preset → fine-tune.
# Based on code review fixes and preset research.
# ------------------------------------------------------------------------------

import os
import io
import re
import json
import shutil
import asyncio
from pathlib import Path
from typing import Dict, Any

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
# 📦  LOAD PRESETS
# ─────────────────────────────────────────────────
_PRESETS_PATH = os.path.join(os.path.dirname(__file__), "docs", "presets.json")
_PRESETS_DATA: Dict[str, Any] = {}

def _load_presets() -> Dict[str, Any]:
    """Load presets from JSON file."""
    global _PRESETS_DATA
    try:
        with open(_PRESETS_PATH, "r") as f:
            _PRESETS_DATA = json.load(f)
        log("IMAGE", f"Loaded {len(_PRESETS_DATA.get('presets', {}))} presets from presets.json")
    except Exception as e:
        log("IMAGE", f"Failed to load presets: {e}, using empty presets")
        _PRESETS_DATA = {"presets": {}, "parameter_locks": {}, "condition_codes": []}

def _get_preset(condition: str) -> Dict[str, Any]:
    """Get preset params for a condition code."""
    presets = _PRESETS_DATA.get("presets", {})
    if condition in presets:
        return presets[condition].get("params", {})
    return {}

def _get_locks(condition: str) -> Dict[str, Any]:
    """Get parameter locks for a condition."""
    locks = _PRESETS_DATA.get("parameter_locks", {})
    return locks.get(condition, {})

def _apply_locks(params: Dict[str, Any], locks: Dict[str, Any]) -> Dict[str, Any]:
    """Apply parameter locks — clamp values to allowed ranges."""
    if not locks:
        return params

    result = params.copy()

    # Handle range locks (e.g., "c": [0.90, 1.05])
    for key, val in locks.items():
        if key.endswith("_min") or key.endswith("_max"):
            continue
        if isinstance(val, list) and len(val) == 2:
            if key in result:
                result[key] = np.clip(result[key], val[0], val[1])

    # Handle min locks (e.g., "d_min": 30)
    for key, val in locks.items():
        if key.endswith("_min"):
            param_key = key[:-4]
            if param_key in result:
                result[param_key] = max(result[param_key], val)

    # Handle max locks (e.g., "s_max": 0.95)
    for key, val in locks.items():
        if key.endswith("_max"):
            param_key = key[:-4]
            if param_key in result:
                result[param_key] = min(result[param_key], val)

    return result


# Load presets at import time
_load_presets()


# ─────────────────────────────────────────────────
# 🤖  PROMPTS
# ─────────────────────────────────────────────────

# Pass 1: Classification prompt
CLASSIFY_PROMPT = (
    "Analyze this photo and output ONLY ONE of these condition codes, nothing else:\n\n"
    "DAYLIGHT | OVERCAST | LOWLIGHT | BACKLIGHT | GOLDEN_HR | HIGH_KEY |\n"
    "GREEN_SPILL | GREEN_CAST | NEON | PORTRAIT | SKIN_WARM | SKIN_PALE |\n"
    "WINDOW_LIGHT | NIGHT | HAZE | BLUE_SKY_SPILL\n\n"
    "Rules:\n"
    "- Output ONLY the code, one word, no explanation.\n"
    "- If multiple conditions, pick the MOST dominant one.\n"
    "- If unsure, output DAYLIGHT.\n"
)

# Pass 2: Correction prompt
CORRECT_PROMPT_TEMPLATE = (
    "You are a professional photo colorist. A photo has been classified as: {condition}\n\n"
    "Base preset for this condition:\n{preset_json}\n\n"
    "Fine-tune the parameters based on the actual image. Adjust only what differs from the base.\n"
    "Consider: skin tones, color cast, exposure, contrast, detail.\n\n"
    "OUTPUT FORMAT (return ONLY this JSON, no markdown):\n"
    '{{"b":0,"c":1.0,"s":1.0,"v":1.0,"h":0,"d":0,"k":0,"n":0,"w":0,"t":0,"p":1.0,"l":0,"x":"diagnosis"}}\n\n'
    "PARAMETERS:\n"
    "b = brightness  (-80..80)    c = contrast    (0.6..2.0)\n"
    "s = saturation  (0.5..2.0)   v = vibrance    (0.8..2.0)\n"
    "h = highlights  (-80..20)    d = shadows     (-20..80)\n"
    "k = blacks      (-60..15)    n = whites      (0..60)\n"
    "w = warmth      (-40..40)    t = tint        (-30..30)\n"
    "p = sharpness   (0.5..2.0)   l = clarity     (-20..60)\n"
    "x = description (max 12 words)\n\n"
    "PARAMETER LOCKS (non-negotiable):\n"
    "- BACKLIGHT: c=0.90..1.05, d>=+30, h<=-25\n"
    "- GREEN_SPILL: t=+10..+28, s<=0.95\n"
    "- LOWLIGHT: b>=+15, d>=+20, c>=1.0\n"
    "- PORTRAIT: l=-8..-15, p=0.8..0.95, v<=1.2\n"
    "- SKIN (any): v<=1.3, s<=1.2\n\n"
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

# WARN-01: Truly neutral defaults (no correction applied)
DEFAULT_PARAMS = {
    "brightness": 0,  "contrast": 1.0,  "saturation": 1.0,
    "vibrance": 1.0,  "highlights": 0,  "shadows": 0,
    "blacks": 0,      "whites": 0,      "warmth": 0,
    "tint": 0,        "sharpness": 1.0, "clarity": 0,
    "description": "fallback: no correction (analysis failed)",
}


# ─────────────────────────────────────────────────
# 🤖  TWO-PASS IMAGE ANALYSIS
# ─────────────────────────────────────────────────
def analyze_image(image_path: str, gemini_client) -> Dict[str, Any]:
    """
    Two-pass analysis:
      Pass 1: Classify condition (one code)
      Pass 2: Fine-tune preset for that condition
    """
    img = Image.open(image_path).convert("RGB")
    if max(img.size) > 768:
        img.thumbnail((768, 768), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    img_bytes = buf.getvalue()

    try:
        from google.genai import types

        # ── Pass 1: Classify ──────────────────────────────────────
        log("IMAGE", "Pass 1: Classifying condition...")
        resp1 = gemini_client.models.generate_content(
            model=GEMMA_MODEL,
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                CLASSIFY_PROMPT,
            ],
            config=types.GenerateContentConfig(
                system_instruction="You are a photo condition classifier. Output ONLY the condition code.",
                temperature=0.1,
            ),
        )

        condition = resp1.text.strip().upper().replace('"', '').replace("'", "")
        # Clean up — take first valid code
        valid_codes = _PRESETS_DATA.get("condition_codes", [])
        if condition not in valid_codes:
            # Try to find a match
            for code in valid_codes:
                if code in condition:
                    condition = code
                    break
            else:
                condition = "DAYLIGHT"

        log("IMAGE", f"Pass 1 result: {condition}")

        # ── Pass 2: Fine-tune preset ──────────────────────────────
        preset = _get_preset(condition)
        if not preset:
            log("IMAGE", f"No preset for {condition}, using DAYLIGHT")
            condition = "DAYLIGHT"
            preset = _get_preset("DAYLIGHT")

        preset_json = json.dumps(preset, indent=2)
        prompt2 = CORRECT_PROMPT_TEMPLATE.format(
            condition=condition,
            preset_json=preset_json,
        )

        log("IMAGE", "Pass 2: Fine-tuning parameters...")
        resp2 = gemini_client.models.generate_content(
            model=GEMMA_MODEL,
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                prompt2,
            ],
            config=types.GenerateContentConfig(
                system_instruction="You are a professional photo colorist. Output ONLY the JSON.",
                temperature=0.1,
            ),
        )

        if resp2.text is None:
            raise ValueError("Empty response from Pass 2")

        text = resp2.text.strip()

        # Safety filter
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

        # Apply parameter locks
        locks = _get_locks(condition)
        result = _apply_locks(result, locks)

        # Add condition to description
        result["condition"] = condition
        if "description" in result:
            result["description"] = f"[{condition}] {result['description']}"

        return result

    except Exception as e:
        log("IMAGE", f"Analysis failed: {e}, using default")
        return DEFAULT_PARAMS.copy()


# ─────────────────────────────────────────────────
# 🖼️  CONTRAST LUT (S-curve via tanh) — WARN-02 fix
# ─────────────────────────────────────────────────
def build_contrast_lut(contrast: float) -> np.ndarray:
    """
    S-curve contrast LUT using tanh.
    contrast=1.0 -> identity, >1.0 -> more contrast, <1.0 -> less.
    Soft shoulder protects shadow/highlight detail.
    """
    if abs(contrast - 1.0) < 0.01:
        return np.arange(256, dtype=np.uint8)

    k = (contrast - 1.0) * 4.0
    x = np.arange(256, dtype=np.float32) / 255.0
    denom = 2.0 * np.tanh(k * 0.5) + 1e-6
    y = 0.5 + np.tanh(k * (x - 0.5)) / denom
    return np.clip(y * 255, 0, 255).astype(np.uint8)


# ─────────────────────────────────────────────────
# 🖼️  BACKLIGHT DETECTION — BUG-02 fix
# ─────────────────────────────────────────────────
def is_backlight(img: np.ndarray) -> bool:
    """
    Improved backlight detection: center subject must be dark
    compared to edges (top/bottom background).
    """
    gray = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = gray.shape

    # Subject center region
    center = gray[int(h*0.25):int(h*0.75), int(w*0.25):int(w*0.75)]
    # Background: top and bottom edges
    bg_top = gray[:int(h*0.15), :]
    bg_bot = gray[int(h*0.85):, :]
    edges = np.concatenate([bg_top.ravel(), bg_bot.ravel()])

    mean_center = np.mean(center)
    mean_edges = np.mean(edges)

    # Backlight: center dark (<120), edges much brighter, gap >60
    detected = (mean_edges - mean_center) > 60 and mean_center < 120
    if detected:
        log("IMAGE", f"Backlight: center={mean_center:.1f} edges={mean_edges:.1f}")
    return detected


# ─────────────────────────────────────────────────
# 🖼️  GRAY WORLD AUTO WHITE BALANCE — BUG-01 fix
# ─────────────────────────────────────────────────
def gray_world_wb(img: np.ndarray, strength: float = 0.5) -> np.ndarray:
    """
    Gray World auto white balance.
    Only applied when LLM doesn't detect specific cast.
    """
    avg_b = np.mean(img[:, :, 0])
    avg_g = np.mean(img[:, :, 1])
    avg_r = np.mean(img[:, :, 2])
    avg = (avg_b + avg_g + avg_r) / 3.0

    scale_b = (avg / avg_b) ** strength
    scale_g = (avg / avg_g) ** strength
    scale_r = (avg / avg_r) ** strength

    img[:, :, 0] = np.clip(img[:, :, 0] * scale_b, 0, 255)
    img[:, :, 1] = np.clip(img[:, :, 1] * scale_g, 0, 255)
    img[:, :, 2] = np.clip(img[:, :, 2] * scale_r, 0, 255)

    log("IMAGE", f"Gray World: B×{scale_b:.2f} G×{scale_g:.2f} R×{scale_r:.2f}")
    return img


# ─────────────────────────────────────────────────
# 🖼️  QUALITY GUARD — WARN-03 fix (comprehensive)
# ─────────────────────────────────────────────────
def quality_guard(original: np.ndarray, result: np.ndarray) -> bool:
    """Return True if edit worsens the photo significantly."""
    # Check highlight clipping — higher threshold to avoid false positives
    # on lowlight/backlight photos where shadow lift is expected
    clip_before = np.mean(original > 250)
    clip_after = np.mean(result > 250)
    if clip_after > clip_before + 0.15 and clip_after > 0.30:
        log("IMAGE", f"Quality guard: highlight clip worse ({clip_before:.3f} → {clip_after:.3f})")
        return True

    # Check green cast
    ge_before = float(np.mean(original[:, :, 1]) - (np.mean(original[:, :, 0]) + np.mean(original[:, :, 2])) / 2.0)
    ge_after = float(np.mean(result[:, :, 1]) - (np.mean(result[:, :, 0]) + np.mean(result[:, :, 2])) / 2.0)
    if ge_after > ge_before + 5:
        log("IMAGE", f"Quality guard: green cast worse ({ge_before:.1f} → {ge_after:.1f})")
        return True

    return False


# ─────────────────────────────────────────────────
# 🖼️  OPENCV: APPLY COLOR CORRECTIONS
# — BUG-01 (GW skip), BUG-03 (norm_original), WARN-04 (divisor 150)
# ─────────────────────────────────────────────────
def apply_corrections(input_path: str, params: Dict[str, Any], output_path: str) -> str:
    """Apply color corrections using OpenCV pipeline."""
    img_bgr = cv2.imread(input_path, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise IOError(f"Cannot read: {input_path}")

    original_bgr = img_bgr.copy()
    img = img_bgr.astype(np.float32)

    # ── BUG-01 fix: Skip Gray World if LLM detected specific cast ──────
    warmth = params.get("warmth", 0)
    tint = params.get("tint", 0)
    has_cast = abs(warmth) > 8 or abs(tint) > 8

    if not is_backlight(img):
        if not has_cast:
            img = gray_world_wb(img, strength=0.5)
        else:
            # Light pre-normalization when LLM detected cast
            img = gray_world_wb(img, strength=0.2)

    # ── BUG-03 fix: Save norm BEFORE brightness/contrast ────────────────
    norm_original = np.clip(img.copy(), 0, 255) / 255.0

    # 1. WHITE BALANCE — Warmth & Tint — WARN-04 fix (divisor 150)
    wb_r = 1.0 + warmth / 150.0   # warmth +40 → R × 1.267
    wb_b = 1.0 - warmth / 150.0
    wb_g = 1.0 - tint / 150.0     # tint +25 → G × 0.833

    img[:, :, 2] = np.clip(img[:, :, 2] * wb_r, 0, 255)  # Red
    img[:, :, 0] = np.clip(img[:, :, 0] * wb_b, 0, 255)  # Blue
    img[:, :, 1] = np.clip(img[:, :, 1] * wb_g, 0, 255)  # Green

    # 2. EXPOSURE — Brightness
    img = np.clip(img + params.get("brightness", 0) * 2.0, 0, 255)

    # 3. CONTRAST — S-curve LUT (WARN-02 fix)
    lut = build_contrast_lut(params.get("contrast", 1.0))
    img = cv2.LUT(img.astype(np.uint8), lut).astype(np.float32)

    # 4. HIGHLIGHTS & SHADOWS — BUG-03 fix (use norm_original)
    img += params.get("highlights", 0) / 100.0 * (norm_original ** 2) * 100.0
    img += params.get("shadows", 0) / 100.0 * ((1.0 - norm_original) ** 2) * 100.0
    img = np.clip(img, 0, 255)

    # 5. BLACKS & WHITES — BUG-03 fix (use norm_original)
    img += params.get("blacks", 0) / 100.0 * ((1.0 - norm_original) ** 3) * 150.0
    img += params.get("whites", 0) / 100.0 * (norm_original ** 3) * 150.0
    img = np.clip(img, 0, 255)

    # 6. SATURATION + VIBRANCE
    hsv = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
    s_original = hsv[:, :, 1].copy()
    s = np.clip(s_original * params.get("saturation", 1.0), 0, 255)

    # Vibrance: boost low-sat areas
    low_sat_mask = (1.0 - s_original / 255.0) ** 2
    vib_factor = params.get("vibrance", 1.0)
    effective_vib = 1.0 + (vib_factor - 1.0) * low_sat_mask
    s = np.clip(s * effective_vib, 0, 255)

    hsv[:, :, 1] = s
    img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)

    # 7. CLARITY & SHARPNESS
    h_px, w_px = img.shape[:2]

    # Clarity
    sigma_clarity = max(h_px, w_px) * 0.004
    clarity = params.get("clarity", 0)
    if clarity != 0:
        u8 = img.astype(np.uint8)
        blurred = cv2.GaussianBlur(u8, (0, 0), sigmaX=sigma_clarity)
        lum = cv2.cvtColor(u8, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        mid = 4.0 * lum * (1.0 - lum)
        img = np.clip(img + (clarity / 100.0) * (img - blurred.astype(np.float32))
                      * mid[:, :, np.newaxis], 0, 255)

    # Sharpness
    sigma_sharp = max(h_px, w_px) * 0.0006
    sharp = params.get("sharpness", 1.0)
    if sharp != 1.0:
        u8 = img.astype(np.uint8)
        blurred = cv2.GaussianBlur(u8, (0, 0), sigmaX=sigma_sharp)
        img = np.clip(img + (sharp - 1.0) * (img - blurred.astype(np.float32)) * 2, 0, 255)

    result = img.astype(np.uint8)

    # ── WARN-03 fix: Comprehensive quality guard ───────────────
    if quality_guard(original_bgr, result):
        log("IMAGE", "Quality guard triggered, using original")
        shutil.copy(input_path, output_path)
        return output_path

    # Save
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
    Main entry point: two-pass analyze with Gemma 4, apply corrections with OpenCV.
    Returns dict with status and parameters used.
    """
    try:
        # 1. Two-pass analyze
        params = await asyncio.to_thread(analyze_image, input_path, gemini_client)

        # 2. Apply corrections
        await asyncio.to_thread(apply_corrections, input_path, params, output_path)

        condition = params.get("condition", "UNKNOWN")
        log("IMAGE", f"Edited [{condition}]: {os.path.basename(input_path)} → {params.get('description', 'ok')}")

        return {
            "status": "success",
            "params": params,
            "condition": condition,
            "output_path": output_path,
        }

    except Exception as e:
        log("IMAGE", f"Edit failed: {e}")
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
