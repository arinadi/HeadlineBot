# 🤖 Model Manager - HeadlineBot
# ------------------------------------------------------------------------------
# Smart model discovery: fetch available models, filter flash/gemma,
# sort by version (newest first), use as primary + fallback chain.
# ------------------------------------------------------------------------------

import re
from typing import List, Optional
from utils import log


# Categories for model filtering
MODEL_CATEGORIES = {
    "flash": ["flash"],      # Gemini Flash models
    "gemma": ["gemma"],      # Gemma models
}


def extract_version(model_name: str) -> tuple:
    """
    Extract version number from model name for sorting.
    Examples:
      'gemini-3.5-flash' → (3, 5)
      'gemini-2.5-flash-preview-tts' → (2, 5)
      'gemma-4-26b-a4b-it' → (4, 26)
      'gemini-flash-latest' → (999, 0)  # 'latest' = highest priority
    """
    name = model_name.lower()

    # Handle 'latest' models - give them highest version
    if 'latest' in name:
        return (999, 0)

    # Extract numbers from the model name
    numbers = re.findall(r'(\d+)', name)

    if not numbers:
        return (0, 0)

    # For gemma models: version is first number, params is second
    if 'gemma' in name:
        version = int(numbers[0])
        params = int(numbers[1]) if len(numbers) > 1 else 0
        return (version, params)

    # For gemini models: major.minor version
    if len(numbers) >= 2:
        major = int(numbers[0])
        minor = int(numbers[1])
        return (major, minor)
    elif len(numbers) == 1:
        return (int(numbers[0]), 0)

    return (0, 0)


def filter_models(
    all_models: List[str],
    categories: List[str] = None
) -> List[str]:
    """
    Filter models by category (flash, gemma, or both).
    Returns filtered list sorted by version (newest first).
    """
    if categories is None:
        categories = list(MODEL_CATEGORIES.keys())

    # Build filter keywords
    keywords = []
    for cat in categories:
        if cat in MODEL_CATEGORIES:
            keywords.extend(MODEL_CATEGORIES[cat])

    # Filter models
    filtered = []
    for model in all_models:
        model_lower = model.lower()
        if any(kw in model_lower for kw in keywords):
            # Exclude TTS, image, robotics, embed, etc. unless explicitly requested
            if not any(skip in model_lower for skip in ['-tts', '-image', 'robotics', 'embedding', 'lyria', 'nano-banana', 'antigravity', 'deep-research']):
                filtered.append(model)

    # Sort by version (newest first)
    filtered.sort(key=lambda m: extract_version(m), reverse=True)

    return filtered


def build_model_chain(
    all_models: List[str],
    primary_category: str = "flash",
    fallback_categories: List[str] = None
) -> dict:
    """
    Build a model chain: primary + fallbacks.
    Returns dict with 'primary' and 'fallbacks' keys.
    """
    # Get primary models (newest version)
    primary_models = filter_models(all_models, [primary_category])
    primary = primary_models[0] if primary_models else None

    # Get fallback models (all other flash/gemma models)
    if fallback_categories is None:
        fallback_categories = ["flash", "gemma"]

    all_filtered = filter_models(all_models, fallback_categories)
    fallbacks = [m for m in all_filtered if m != primary]

    return {
        "primary": primary,
        "fallbacks": fallbacks,
        "all": [primary] + fallbacks if primary else fallbacks,
    }


async def discover_models(gemini_client) -> dict:
    """
    Discover all available models and build smart model chains.
    Called once at startup.

    Returns dict with:
      - 'transcript': chain for transcription (flash models)
      - 'summary': chain for summarization (gemma models)
      - 'retouch': chain for retouch (gemma models)
      - 'photo': chain for photo editing (gemma models)
      - 'all': all available model names
    """
    log("MODEL", "Discovering available models...")

    try:
        # Fetch all models
        all_models = []
        for m in gemini_client.models.list():
            for action in m.supported_actions:
                if action == "generateContent":
                    all_models.append(m.name)

        log("MODEL", f"Found {len(all_models)} models with generateContent")

        # Build model chains
        transcript_chain = build_model_chain(all_models, "flash", ["flash"])
        gemma_chain = build_model_chain(all_models, "gemma", ["gemma", "flash"])

        result = {
            "transcript": transcript_chain,
            "summary": gemma_chain,      # Prefer gemma, fallback flash
            "retouch": gemma_chain,      # Same as summary
            "photo": gemma_chain,        # Same as summary
            "all": all_models,
        }

        # Log results
        log("MODEL", f"Transcript primary: {transcript_chain['primary']}")
        log("MODEL", f"Summary/Retouch/Photo primary: {gemma_chain['primary']}")
        if transcript_chain['fallbacks']:
            log("MODEL", f"Transcript fallbacks: {len(transcript_chain['fallbacks'])} models")
        if gemma_chain['fallbacks']:
            log("MODEL", f"Gemma fallbacks: {len(gemma_chain['fallbacks'])} models")

        return result

    except Exception as e:
        log("ERROR", f"Model discovery failed: {e}")
        # Return minimal defaults — let try_model_chain handle failures gracefully
        return {
            "transcript": {"primary": None, "fallbacks": [], "all": []},
            "summary": {"primary": None, "fallbacks": [], "all": []},
            "retouch": {"primary": None, "fallbacks": [], "all": []},
            "photo": {"primary": None, "fallbacks": [], "all": []},
            "all": [],
        }


async def try_model_chain(
    gemini_client,
    model_chain: dict,
    contents,
    config=None,
    task_name: str = "task"
) -> Optional[object]:
    """
    Try models in chain order (primary → fallbacks).
    Returns first successful response, or None if all fail.
    """
    models_to_try = model_chain.get("all", [])
    if not models_to_try:
        log("ERROR", f"No models available for {task_name}")
        return None

    for model_name in models_to_try:
        try:
            log("MODEL", f"Trying {model_name} for {task_name}...")
            kwargs = {"model": model_name, "contents": contents}
            if config:
                kwargs["config"] = config

            # generate_content is async — call directly with await
            response = await gemini_client.models.generate_content(**kwargs)

            if response.text:
                log("MODEL", f"Success with {model_name} for {task_name}")
                return response
            else:
                log("MODEL", f"{model_name} returned empty response for {task_name}")

        except Exception as e:
            log("MODEL", f"{model_name} failed for {task_name}: {e}")
            continue

    log("ERROR", f"All models failed for {task_name}")
    return None
