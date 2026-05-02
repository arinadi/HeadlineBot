# start.py

import os
import sys
import subprocess

def check_cuda():
    """Checks if CUDA is available by querying nvidia-smi."""
    try:
        subprocess.run(["nvidia-smi"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True, "GPU Detected"
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False, "No GPU detected (nvidia-smi failed or missing)"

def main():
    print("🔍 TTB Smart Runner: Detecting Environment...")
    
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
    print(f"🚀 Starting TTB in {mode} Mode...")
    
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
