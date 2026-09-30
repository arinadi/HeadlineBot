"""Photo analysis must use the base preset of the classified condition and
enforce the non-negotiable parameter locks from presets.json."""
import json
from pathlib import Path

import pytest
from PIL import Image

from headlinebot.image_editor import analyze_image
from tests.fakes import FakeGeminiClient

PRESETS = json.loads((Path(__file__).parent.parent / "presets.json").read_text())


@pytest.fixture
def photo(tmp_path):
    path = tmp_path / "photo.jpg"
    Image.new("RGB", (32, 32), (120, 110, 100)).save(path)
    return str(path)


def analyze(photo, condition, correction):
    client = FakeGeminiClient([condition, correction])
    return analyze_image(photo, client), client


def test_known_condition_code_is_kept(photo):
    result, _ = analyze(photo, "NIGHT", "{}")
    assert result["condition"] == "NIGHT"


def test_fine_tune_prompt_contains_the_conditions_base_preset(photo):
    _, client = analyze(photo, "OVERCAST", "{}")
    fine_tune_prompt = client.models.calls[1].contents[1]
    base_preset = PRESETS["presets"]["OVERCAST"]["params"]
    assert base_preset
    assert json.dumps(base_preset, indent=2) in fine_tune_prompt


def test_backlight_lock_lifts_shadows_and_cuts_highlights(photo):
    result, _ = analyze(photo, "BACKLIGHT", '{"d": 0, "h": 0}')
    assert result["shadows"] >= 30
    assert result["highlights"] <= -30


def test_portrait_lock_keeps_clarity_negative_and_sharpness_soft(photo):
    result, _ = analyze(photo, "PORTRAIT", '{"l": 10, "p": 1.5, "v": 1.6}')
    assert -15 <= result["clarity"] <= -8
    assert 0.8 <= result["sharpness"] <= 0.95
    assert result["vibrance"] <= 1.2


@pytest.mark.parametrize("condition", ["SKIN_WARM", "SKIN_PALE"])
def test_skin_conditions_cap_vibrance_and_saturation(photo, condition):
    result, _ = analyze(photo, condition, '{"v": 2.0, "s": 2.0}')
    assert result["vibrance"] <= 1.3
    assert result["saturation"] <= 1.2
