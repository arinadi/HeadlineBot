from headlinebot.model_manager import build_model_chain, filter_models


def test_filter_models_orders_newest_first_with_latest_on_top():
    models = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-3.5-flash"]
    assert filter_models(models, ["flash"]) == ["gemini-flash-latest", "gemini-3.5-flash", "gemini-2.5-flash"]


def test_filter_models_drops_non_text_variants():
    models = ["gemini-3.5-flash", "gemini-2.5-flash-preview-tts", "gemini-2.5-flash-image", "text-embedding-004"]
    assert filter_models(models, ["flash"]) == ["gemini-3.5-flash"]


def test_filter_models_ranks_gemma_by_version_then_size():
    models = ["gemma-3-27b-it", "gemma-4-26b-a4b-it", "gemma-4-31b-it"]
    assert filter_models(models, ["gemma"]) == ["gemma-4-31b-it", "gemma-4-26b-a4b-it", "gemma-3-27b-it"]


def test_build_model_chain_puts_primary_first_without_duplicating_it():
    chain = build_model_chain(["gemma-4-31b-it", "gemma-4-26b-a4b-it"], "gemma", ["gemma"])
    assert chain["primary"] == "gemma-4-31b-it"
    assert chain["all"] == ["gemma-4-31b-it", "gemma-4-26b-a4b-it"]
