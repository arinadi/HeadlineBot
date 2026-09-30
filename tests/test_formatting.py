from headlinebot.utils import format_duration


def test_format_duration_shows_minutes_and_zero_padded_seconds():
    assert format_duration(125) == "2m 05s"


def test_format_duration_truncates_fractional_seconds():
    assert format_duration(59.9) == "0m 59s"


def test_format_duration_rejects_negative_or_non_numeric():
    assert format_duration(-1) == "N/A"
    assert format_duration("12") == "N/A"
