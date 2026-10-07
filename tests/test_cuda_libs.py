"""cuda_libs.preload_cuda12_libs: load the CUDA 12 cuBLAS/cuDNN shipped as pip
wheels (nvidia-cublas-cu12, nvidia-cudnn-cu12) so CTranslate2 finds them."""

import ctypes
import sys

import pytest

from headlinebot import cuda_libs

# Fake dependency graph of the real wheels: a lib fails to load until the libs it links are loaded.
NEEDS = {
    "libcublas.so.12": {"libcublasLt.so.12"},
    "libcudnn_ops.so.9": {"libcudnn_graph.so.9"},
    "libcudnn.so.9": set(),
}


@pytest.fixture
def fresh_nvidia(monkeypatch):
    # `nvidia` is a namespace package; drop any cached copy so each test sees its own sys.path.
    for name in [m for m in sys.modules if m == "nvidia" or m.startswith("nvidia.")]:
        monkeypatch.delitem(sys.modules, name)


@pytest.fixture
def loaded(monkeypatch):
    calls = []

    def fake_cdll(path, mode=0):
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        if not NEEDS.get(name, set()) <= {n for n, _ in calls}:
            raise OSError(f"{name}: cannot open shared object file")
        calls.append((name, mode))

    monkeypatch.setattr(cuda_libs, "CDLL", fake_cdll)
    return calls


def make_wheels(root):
    for pkg, libs in {
        "cublas": ["libcublas.so.12", "libcublasLt.so.12"],
        "cudnn": ["libcudnn_ops.so.9", "libcudnn_graph.so.9", "libcudnn.so.9"],
    }.items():
        lib_dir = root / "nvidia" / pkg / "lib"
        lib_dir.mkdir(parents=True)
        (root / "nvidia" / pkg / "__init__.py").write_text("")
        for lib in libs:
            (lib_dir / lib).write_bytes(b"")


def test_loads_every_cublas_and_cudnn_lib_globally_in_dependency_order(tmp_path, monkeypatch, fresh_nvidia, loaded):
    make_wheels(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    cuda_libs.preload_cuda12_libs()

    assert sorted(n for n, _ in loaded) == sorted(
        ["libcublas.so.12", "libcublasLt.so.12", "libcudnn_ops.so.9", "libcudnn_graph.so.9", "libcudnn.so.9"]
    )
    assert all(mode == ctypes.RTLD_GLOBAL for _, mode in loaded)


def test_loads_nothing_when_the_cuda12_wheels_are_not_installed(tmp_path, monkeypatch, fresh_nvidia, loaded):
    monkeypatch.syspath_prepend(str(tmp_path))  # empty dir; no nvidia wheels anywhere on a dev box

    cuda_libs.preload_cuda12_libs()

    assert loaded == []
