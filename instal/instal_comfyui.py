#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
instal_comfyui.py
=================================================================
STEP 1 of 3. Installs ComfyUI and the ComfyUI-Manager node.

What's done here for SPEED and CONFLICT PREVENTION:
  * venv is created via `uv` instead of `virtualenv` — package installation
    is much faster (uv installs torch and dependencies in parallel).
  * Python 3.12 — stable wheels for torch cu130, fast interpreter.
    Uses uv-managed CPython (not dependent on what's in the Kaggle image).
  * torch built for CUDA 13.0 (cu130) — Kaggle driver (580.x) supports it,
    and ComfyUI 0.24 enables optimized CUDA operations on it (cu128 had
    a warning and slower path). Tested on 2× T4.
  * xformers NOT installed: recent xformers builds don't contain kernels for
    Turing (T4, compute 7.5) and only slow things down.
  * SageAttention-SM75-path (github.com/THE-ANGEL-AI/SageAttention-SM75-path):
    fork with Turing (sm_75) support via CUDA kernel
    `sageattn_qk_int8_pv_fp16_cuda_sm75`. Installed at runtime
    from start.py (direct pip, not uv — uv handles CUDA extensions poorly).
    Falls back to split-cross-attention if installation fails.
  * T4-aware: --use-sage-attention if Sage is installed,
    otherwise --use-split-cross-attention.
  * Do NOT install tensorflow or old diffusers/transformers — they pull
    their own versions of CUDA/numerical libraries and conflict.
    Modern versions come with custom node requirements (step 2).

Run (in notebook):  !python instal/instal_comfyui.py

The script is IDEMPOTENT: each step first checks whether it's already done
(uv installed? venv intact? torch with CUDA in place? repos cloned?),
and skips redundant work. Safe to re-run.

All path/uv/venv logic lives in the shared module kaggle_env.py — single
source of truth for all three steps (uv persistence fix is there too).
=================================================================
"""

import os
import shutil
import subprocess
import sys

# Shared module is next to this file — imported by absolute path,
# not dependent on current directory (run as `!python instal/instal_comfyui.py`).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kaggle_env as ke
from kaggle_env import (
    HOME_DIR, COMFY_DIR, VENV_PYTHON,
    log, warn, step, run, uv_pip_install,
    install_python,
)

# ----------------------------------------------------------------------
# Parameters specific to step 1 (paths/uv/venv are in kaggle_env.py).
# ----------------------------------------------------------------------
# CUDA 13.0: Kaggle driver (580.x) supports it, and ComfyUI 0.24 on cu130
# enables optimized CUDA operations (cu128 had a warning and slower path).
# Tested on 2× T4: both GPUs work, warning disappears.
# If you need to roll back to 12.8 — set cu128.
TORCH_INDEX  = "https://download.pytorch.org/whl/cu130"  # CUDA 13.0

COMFYUI_REPO = "https://github.com/Comfy-Org/ComfyUI.git"
MANAGER_REPO = "https://github.com/ltdrdata/ComfyUI-Manager.git"


# ----------------------------------------------------------------------
# 1. System packages (ffmpeg for video/preview nodes).
# ----------------------------------------------------------------------
def install_system_packages():
    step("System packages (ffmpeg)")
    if shutil.which("ffmpeg"):
        log("ffmpeg already installed (skipping apt)")
        return
    run("apt-get update -qq", check=False)
    run("apt-get install -y -qq ffmpeg", check=False)


# ----------------------------------------------------------------------
# 2. uv + venv (all logic is in kaggle_env, here just the sequence).
# ----------------------------------------------------------------------
def setup_uv_venv():
    install_python()


# ----------------------------------------------------------------------
# 3. PyTorch for CUDA 13.0 (key for generation speed).
# ----------------------------------------------------------------------
def install_torch():
    step("PyTorch for CUDA 13.0 (cu130)")
    if ke.torch_cuda_ok():
        log("torch with working CUDA already installed (reinstall skipped)")
    else:
        uv_pip_install(
            "torch==2.11.0", "torchvision==0.26.0", "torchaudio==2.11.0",
            extra_args=["--index-url", TORCH_INDEX],
        )

    # nvidia-ml-py — torch imports pynvml (module from nvidia-ml-py).
    # Install immediately so torch.cuda doesn't trip.
    uv_pip_install("nvidia-ml-py")
    # NB: we don't remove the pynvml redirect here — it may reinstall
    # when ComfyUI/nodes are installed. Final cleanup in main().

    # Check that torch sees CUDA — catch the problem immediately, not at launch.
    run([VENV_PYTHON, "-c",
         "import torch; "
         "print('Torch:', torch.__version__); "
         "print('CUDA build:', torch.version.cuda); "
         "print('CUDA available:', torch.cuda.is_available()); "
         "print('GPU count:', torch.cuda.device_count())"],
        check=False)


# ----------------------------------------------------------------------
# 4. ComfyUI: clone + its dependencies.
# ----------------------------------------------------------------------
def install_comfyui():
    step("ComfyUI")
    if not os.path.exists(COMFY_DIR):
        run(["git", "clone", COMFYUI_REPO, COMFY_DIR])
    else:
        run(["git", "-C", COMFY_DIR, "pull"], check=False)

    uv_pip_install("-r", f"{COMFY_DIR}/requirements.txt")
    log("ComfyUI and its dependencies installed")


# ----------------------------------------------------------------------
# 5. ComfyUI-Manager (node manager — installed here per spec).
# ----------------------------------------------------------------------
def install_manager():
    step("ComfyUI-Manager node")
    manager_dir = f"{COMFY_DIR}/custom_nodes/ComfyUI-Manager"
    if not os.path.exists(manager_dir):
        run(["git", "clone", MANAGER_REPO, manager_dir])
    else:
        run(["git", "-C", manager_dir, "pull"], check=False)

    req = f"{manager_dir}/requirements.txt"
    if os.path.exists(req):
        uv_pip_install("-r", req)
    log("ComfyUI-Manager installed")


# ----------------------------------------------------------------------
# 6. Small set of common packages useful for most nodes.
#    (Modern versions, no old pins — to avoid conflicts.)
# ----------------------------------------------------------------------
def install_common_extras():
    step("Common helper packages")
    uv_pip_install(
        "nvidia-ml-py",   # GPU monitoring (Crystools)
        "einops",
        "omegaconf",
        "timm",
        "mediapy",
        "loguru",
        "imageio[ffmpeg]", "opencv-python", "ffmpeg-python",
    )
    log("Helper packages installed")


def main():
    step("STEP 1: Installing ComfyUI and Manager (uv + torch cu130)")
    os.chdir(HOME_DIR)

    install_system_packages()
    setup_uv_venv()
    install_torch()
    install_comfyui()
    install_manager()
    install_common_extras()

    # Final pynvml redirect cleanup AFTER all installations.
    # If any requirements.txt pulls pynvml as a dependency,
    # it gets installed back. Only the final uninstall guarantees
    # cleanliness before ComfyUI launch.
    uv_pip_install("nvidia-ml-py")
    run(["uv", "pip", "uninstall", "--python", VENV_PYTHON, "-q", "pynvml"],
        check=False)

    log("DONE. ComfyUI installed. Now run: !python instal/instal_castom_node.py")


if __name__ == "__main__":
    main()
