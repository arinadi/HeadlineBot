# start.py

import os
import subprocess
import sys


def check_cuda():
    """Checks if CUDA is available by querying nvidia-smi.

    NOTE: nvidia-smi proves driver/GPU presence, not torch CUDA support.
    main.py re-checks torch.cuda.is_available() after imports and degrades
    device to CPU if torch lacks CUDA, even when MODE stays WHISPER.
    If WHISPER on CPU proves too slow/OOM, set TRANSCRIPTION_MODE=GEMINI.
    """
    try:
        subprocess.run(["nvidia-smi"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True, "GPU Detected (nvidia-smi; torch CUDA re-checked in main.py)"
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False, "No GPU detected (nvidia-smi failed or missing)"

def main():
    print("🔍 HeadlineBot Smart Runner: Detecting Environment...")

    is_gpu, gpu_reason = check_cuda()

    if is_gpu:
        mode = 'WHISPER'
        print(f"🚀 {gpu_reason}. Transcription Mode: WHISPER")
    else:
        mode = 'GEMINI'
        print(f"⚠️ {gpu_reason}. Transcription Mode: GEMINI (CPU)")

    # Set Environment Variable
    os.environ['TRANSCRIPTION_MODE'] = mode

    # Launch main.py
    print(f"🚀 Starting HeadlineBot in {mode} Mode...")

    try:
        # Use sys.executable to ensure we use the same environment
        cmd = [sys.executable, "main.py"]
        # In Colab/Terminal, we want to see the output in real-time
        process = subprocess.Popen(cmd)
        process.wait()
    except KeyboardInterrupt:
        print("\n🛑 Runner stopped by user.")
    except Exception as e:
        print(f"❌ Runner Error: {e}")

if __name__ == "__main__":
    main()
