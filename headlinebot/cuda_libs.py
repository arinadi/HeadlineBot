"""Make the CUDA 12 cuBLAS/cuDNN from pip wheels visible to CTranslate2 (faster-whisper).

CTranslate2 4.x dlopens libcublas.so.12 and cuDNN 9 by bare name. Colab's newer torch
ships CUDA 13 libs only, so requirements.txt installs nvidia-cublas-cu12 and
nvidia-cudnn-cu12. Their lib dirs are not on the loader path, and LD_LIBRARY_PATH is
read only at process start, so we load them here with RTLD_GLOBAL: a later dlopen of
the same soname then reuses the copy already in memory.
"""

import importlib.util
import os
from ctypes import CDLL, RTLD_GLOBAL

WHEELS = ("nvidia.cublas", "nvidia.cudnn")


def _lib_dirs():
    for package in WHEELS:
        try:
            spec = importlib.util.find_spec(package)
        except ModuleNotFoundError:  # the `nvidia` namespace itself is absent (CPU box, Windows)
            spec = None
        if spec is None:
            continue
        for root in spec.submodule_search_locations or []:
            lib_dir = os.path.join(root, "lib")
            if os.path.isdir(lib_dir):
                yield lib_dir


def preload_cuda12_libs():
    pending = [
        os.path.join(lib_dir, name)
        for lib_dir in _lib_dirs()
        for name in sorted(os.listdir(lib_dir))
        if ".so." in name
    ]
    # The libs link each other (libcublas needs libcublasLt, cuDNN's sub-libs need
    # libcudnn_graph) and the wheels don't document an order, so retry until a pass
    # loads nothing new; whatever is left then is truly broken.
    while pending:
        failed, last_error = [], None
        for path in pending:
            try:
                CDLL(path, mode=RTLD_GLOBAL)
            except OSError as error:
                failed.append(path)
                last_error = error
        if len(failed) == len(pending):
            raise last_error
        pending = failed
