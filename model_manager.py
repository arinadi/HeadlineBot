# 🤖 Model Manager - HeadlineBot
# ------------------------------------------------------------------------------
# Smart model discovery: fetch available models, filter flash/gemma,
# sort by version (newest first), use as primary + fallback chain.
# ------------------------------------------------------------------------------

import asyncio
import re

from utils import log

# Transient errors that warrant retry before fallback
_TRANSIENT_ERRORS = (
    "RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE_EXCEEDED",
    "503", "429", "500", "timeout", "deadline exceeded",
    "rate limit", "quota", "overloaded",
)


def _is_transient_error(error: Exception) -> bool:
    """Check if an error is transient (retryable)."""
    if isinstance(error, asyncio.TimeoutError):
        return True
    msg = str(error).lower()
    return any(kw in msg for kw in _TRANSIENT_ERRORS)


def _check_safety(response) -> str | None:
    """Check response for safety blocks. Returns error message or None."""
    if response.text:
        return None
    # Check candidates for safety finish reason
    if hasattr(response, 'candidates') and response.candidates:
        candidate = response.candidates[0]
        if hasattr(candidate, 'finish_reason'):
            reason = str(candidate.finish_reason)
            if 'SAFETY' in reason or 'BLOCK' in reason:
                return f"Safety block: {reason}"
    return "Empty response (no text)"


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
    all_models: list[str],
    categories: list[str] = None
) -> list[str]:
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
    all_models: list[str],
    primary_category: str = "flash",
    fallback_categories: list[str] = None
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
                    # Strip 'models/' prefix — generate_content() expects bare name
                    # e.g. "models/gemma-4-31b-it" → "gemma-4-31b-it"
                    model_name = m.name.removeprefix("models/")
                    all_models.append(model_name)

        log("MODEL", f"Found {len(all_models)} models with generateContent")

        # Build model chains
        transcript_chain = build_model_chain(all_models, "flash", ["flash"])
        gemma_chain = build_model_chain(all_models, "gemma", ["gemma"])

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
            log("MODEL", f"Transcript fallbacks ({len(transcript_chain['fallbacks'])}): {', '.join(transcript_chain['fallbacks'][:5])}{'...' if len(transcript_chain['fallbacks']) > 5 else ''}")
        if gemma_chain['fallbacks']:
            log("MODEL", f"Gemma fallbacks ({len(gemma_chain['fallbacks'])}): {', '.join(gemma_chain['fallbacks'][:5])}{'...' if len(gemma_chain['fallbacks']) > 5 else ''}")

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
    task_name: str = "task",
    max_retries: int = 2,
) -> object | None:
    """
    Try models in chain order (primary → fallbacks).
    Retries transient errors before moving to next model.
    Returns first successful response, or None if all fail.
    """
    models_to_try = model_chain.get("all", [])
    if not models_to_try:
        log("ERROR", f"No models available for {task_name}")
        return None

    for model_name in models_to_try:
        for attempt in range(1, max_retries + 1):
            try:
                log("MODEL", f"Trying {model_name} for {task_name} (attempt {attempt})...")
                kwargs = {"model": model_name, "contents": contents}
                if config:
                    kwargs["config"] = config

                # generate_content is SYNC — run in thread to avoid blocking event loop
                response = await asyncio.wait_for(
                    asyncio.to_thread(gemini_client.models.generate_content, **kwargs),
                    timeout=120
                )

                # Check for safety blocks
                safety_err = _check_safety(response)
                if safety_err:
                    log("MODEL", f"{model_name}: {safety_err}")
                    break  # Don't retry safety blocks — skip to next model

                if response.text:
                    log("MODEL", f"Success with {model_name} for {task_name}")
                    return response
                else:
                    log("MODEL", f"{model_name} returned empty response for {task_name}")
                    break  # Empty but not safety — don't retry

            except Exception as e:
                log("MODEL", f"{model_name} failed for {task_name}: {e}")
                if _is_transient_error(e) and attempt < max_retries:
                    wait = 2 ** attempt  # exponential backoff: 2s, 4s
                    log("MODEL", f"Transient error, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                break  # Non-transient or max retries — move to next model

    log("ERROR", f"All models failed for {task_name}")
    return None
