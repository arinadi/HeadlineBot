from headlinebot.utils import md_code


def test_md_code_removes_backticks_that_would_break_a_code_span():
    assert "`" not in md_code("rapat`pagi.m4a")


def test_md_code_keeps_ordinary_filenames_unchanged():
    assert md_code("Doorstop_ambar (1).m4a") == "Doorstop_ambar (1).m4a"
