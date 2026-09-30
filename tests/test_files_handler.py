import pytest

from headlinebot.bot_classes import FilesHandler


@pytest.fixture
def handler(tmp_path):
    return FilesHandler(job_manager=None, upload_folder=str(tmp_path))


@pytest.mark.parametrize("name, base, part", [
    ("interview.zip.001", "interview", "001"),
    ("Rapat Pagi.z.02", "Rapat Pagi", "02"),
    ("a.b.ZIP.010", "a.b", "010"),
])
def test_multipart_pattern_recognizes_split_archive_parts(handler, name, base, part):
    match = handler.multipart_pattern.match(name)
    assert match and match.group(1) == base and match.group(3) == part


@pytest.mark.parametrize("name", ["interview.zip", "audio.mp3", "x.zip.1", "x.zip.0001"])
def test_multipart_pattern_ignores_non_part_files(handler, name):
    assert handler.multipart_pattern.match(name) is None
