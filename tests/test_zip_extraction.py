"""Archives from chat users are untrusted: extract only regular files inside the
target folder, skip OS junk, and reject traversal, absolute paths, symlinks and
zip bombs."""
import stat
import zipfile
from pathlib import Path

import pytest

from headlinebot.bot_classes import extract_zip_safely


def make_zip(path, members):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return str(path)


def test_extracts_audio_and_skips_os_junk(tmp_path):
    archive = make_zip(tmp_path / "in.zip", {
        "a.mp3": b"1", "sub/b.wav": b"2", ".DS_Store": b"x",
        "__MACOSX/._a.mp3": b"x", "sub/.hidden.m4a": b"x",
    })
    out = tmp_path / "out"
    extracted = extract_zip_safely(archive, str(out))
    assert sorted(Path(p).relative_to(out).as_posix() for p in extracted) == ["a.mp3", "sub/b.wav"]
    assert not (out / ".DS_Store").exists()


@pytest.mark.parametrize("bad_name", ["../evil.mp3", "sub/../../evil.mp3", "/etc/evil.mp3"])
def test_rejects_paths_that_escape_the_target(tmp_path, bad_name):
    archive = make_zip(tmp_path / "in.zip", {"ok.mp3": b"1", bad_name: b"2"})
    with pytest.raises(ValueError):
        extract_zip_safely(archive, str(tmp_path / "out"))
    assert not (tmp_path / "evil.mp3").exists()


def test_rejects_symlinks(tmp_path):
    path = tmp_path / "in.zip"
    with zipfile.ZipFile(path, "w") as zf:
        link = zipfile.ZipInfo("link.mp3")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(link, "/etc/passwd")
    with pytest.raises(ValueError):
        extract_zip_safely(str(path), str(tmp_path / "out"))


def test_rejects_archives_over_the_uncompressed_size_cap(tmp_path):
    archive = make_zip(tmp_path / "in.zip", {"a.mp3": b"0" * 2000})
    with pytest.raises(ValueError):
        extract_zip_safely(archive, str(tmp_path / "out"), max_total_bytes=1000)
