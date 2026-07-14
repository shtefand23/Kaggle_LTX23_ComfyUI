#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
instal_castom_node.py
=================================================================
STEP 2 of 3. Installs custom nodes and creates symlinks for models
(like in the original notebook, but without conflicts).

LTX 2.3 video generation workspace with 15+ custom nodes:
  * ComfyUI-LTX2-MultiGPU — Hybrid Split Loader for LTX 2.3 GGUF on 2×T4
  * ComfyUI-MultiGPU (DisTorch2) — official multi-GPU support
  * ComfyUI-VideoHelperSuite — video/audio loading and combining
  * ComfyUI-GGUF, ComfyUI-KJNodes, rgthree, Easy-Use, Inspire, RIFE, etc.

The node list and model symlink list are at the top — edit them there,
you add models and nodes manually.

Run (in notebook):  !python instal/instal_castom_node.py

Before running, the script checks that STEP 1 is complete (uv exists,
working venv, and ComfyUI/custom_nodes folder). If not — exits with a
clear hint. Path/uv/venv logic lives in the shared module kaggle_env.py.
=================================================================
"""

import os
import subprocess
import sys

# Shared module next to file — single source of truth (paths, uv, venv).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kaggle_env import (
    COMFY_DIR, NODES_DIR, VENV_PYTHON,
    log, warn, step, run,
    install_python,
)

# ----------------------------------------------------------------------
# CUSTOM NODE LIST  (name -> git repository).
# Add/remove nodes right here.
# ----------------------------------------------------------------------
CUSTOM_NODES = {
    # ── Core LTX 2.3 ──
    "ComfyUI-LTX2-MultiGPU": "https://github.com/THE-ANGEL-AI/ComfyUI-LTX2-MultiGPU.git",
    "WhatDreamsCost-ComfyUI": "https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI.git",
    # ── Multi-GPU + Utilities ──
    "ComfyUI-MultiGPU":   "https://github.com/pollockjj/ComfyUI-MultiGPU.git",
    "ComfyUI-GGUF":       "https://github.com/city96/ComfyUI-GGUF.git",
    "ComfyUI-KJNodes":    "https://github.com/kijai/ComfyUI-KJNodes.git",
    "ComfyUI-Crystools":  "https://github.com/crystian/ComfyUI-Crystools.git",
    # ── Video / Audio ──
    "ComfyUI-VideoHelperSuite": "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git",
    "ComfyUI-RIFE":       "https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git",
    # ── UI / Workflow ──
    "rgthree-comfy":      "https://github.com/rgthree/rgthree-comfy.git",
    "ComfyUI-Easy-Use":   "https://github.com/yolain/ComfyUI-Easy-Use.git",
    "ComfyUI-Inspire":    "https://github.com/ltdrdata/ComfyUI-Inspire-Pack.git",

    # ── Preprocessors ──
    "comfyui_controlnet_aux": "https://github.com/Fannovel16/comfyui_controlnet_aux.git",
    # ── Impact Pack ──
    "ComfyUI-Impact-Pack": "https://github.com/ltdrdata/ComfyUI-Impact-Pack.git",
}

# ----------------------------------------------------------------------
# MODEL SYMLINKS  (source in /kaggle/input -> ComfyUI folder).
# Dataset: kaggle.com/datasets/martasteiner/ltx-2-3-22b-distilled-1-1-q6-k-gguf
# ----------------------------------------------------------------------
DATASET = "/kaggle/input/ltx-2-3-22b-distilled-1-1-q6-k-gguf"

SYMLINKS = [
    # ── Text Encoders ──
    (f"{DATASET}/gemma-3-12b-it-UD-Q5_K_XL.gguf",
     f"{COMFY_DIR}/models/text_encoders/gemma-3-12b-it-UD-Q5_K_XL.gguf"),

    (f"{DATASET}/ltx-2.3_text_projection_bf16.safetensors",
     f"{COMFY_DIR}/models/text_encoders/ltx-2.3_text_projection_bf16.safetensors"),

    # ── VAE ──
    (f"{DATASET}/LTX23_audio_vae_bf16.safetensors",
     f"{COMFY_DIR}/models/vae/LTX23_audio_vae_bf16.safetensors"),

    (f"{DATASET}/LTX23_video_vae_bf16.safetensors",
     f"{COMFY_DIR}/models/vae/LTX23_video_vae_bf16.safetensors"),

    (f"{DATASET}/taeltx2_3.safetensors",
     f"{COMFY_DIR}/models/vae/taeltx2_3.safetensors"),

    # ── Diffusion Models (GGUF) ──
    (f"{DATASET}/ltx-2.3-22b-distilled-1.1-Q6_K.gguf",
     f"{COMFY_DIR}/models/diffusion_models/ltx-2.3-22b-distilled-1.1-Q6_K.gguf"),

    (f"{DATASET}/ltx-2.3-22b-distilled-1.1-UD-Q5_K_M.gguf",
     f"{COMFY_DIR}/models/diffusion_models/ltx-2.3-22b-distilled-1.1-UD-Q5_K_M.gguf"),

    # ── Upscaler ──
    (f"{DATASET}/ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
     f"{COMFY_DIR}/models/latent_upscale_models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors"),

    # ── LoRAs ──
    (f"{DATASET}/LTX-2.3-22b-AV-LoRA-talking-head-v1.safetensors",
     f"{COMFY_DIR}/models/loras/LTX-2.3-22b-AV-LoRA-talking-head-v1.safetensors"),

    (f"{DATASET}/LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors",
     f"{COMFY_DIR}/models/loras/LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors"),

    (f"{DATASET}/ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors",
     f"{COMFY_DIR}/models/loras/ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors"),
]


def uv_pip_install_req(req_path):
    """Installs node requirements into our venv via uv."""
    result = run(["uv", "pip", "install", "--python", VENV_PYTHON, "-r", req_path], check=False)
    if result and result.returncode != 0:
        warn(f"Failed to install node requirements: {req_path}")


def check_prerequisites():
    """Checks that STEP 1 is complete: uv exists, working venv, custom_nodes."""
    step("Checking environment (STEP 1 result)")

    # install_python() centrally installs/repairs uv + venv (including +x).
    install_python()

    if not os.path.exists(NODES_DIR):
        raise RuntimeError(
            f"Folder {NODES_DIR} not found. "
            "First run: !python instal/instal_comfyui.py"
        )
    log("Environment ready: uv, venv and ComfyUI in place")


# ----------------------------------------------------------------------
# Installing one node: clone (or pull) + its requirements.
# ----------------------------------------------------------------------
def install_node(name, repo):
    target = os.path.join(NODES_DIR, name)
    if not os.path.exists(target):
        run(["git", "clone", repo, target])
    else:
        # If remote URL changed (fork moved) — update it
        cur = subprocess.run(
            ["git", "-C", target, "remote", "get-url", "origin"],
            capture_output=True, text=True).stdout.strip()
        if cur != repo:
            warn(f"Remote URL changed: {cur} → {repo}")
            run(["git", "-C", target, "remote", "set-url", "origin", repo])
        run(["git", "-C", target, "pull"], check=False)

    req = os.path.join(target, "requirements.txt")
    if os.path.exists(req):
        uv_pip_install_req(req)
    log(f"Node ready: {name}")


# ----------------------------------------------------------------------
# Create a symlink to a model (idempotent).
# ----------------------------------------------------------------------
def make_symlink(src, dst):
    if not os.path.exists(src):
        warn(f"Source not found, skipping: {src}")
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.islink(dst) or os.path.exists(dst):
        os.remove(dst)            # recreate so the link is always up-to-date
    os.symlink(src, dst)
    log(f"Link: {os.path.basename(dst)}")


# ----------------------------------------------------------------------
# Auto-inject SageAttention-T4 into workflow
# ----------------------------------------------------------------------
def inject_sageattn_into_workflows():
    print()
    print('\033[96m=== Auto-inject SageAttention-T4 into workflow ===\033[0m', flush=True)

    sage_node_dir = os.path.join(NODES_DIR, 'SageAttention-T4')
    if not os.path.isdir(sage_node_dir):
        warn('SageAttention-T4 node not found in custom_nodes — skipping')
        return

    injector = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'scripts', 'inject_sageattn_workflow.py'
    )

    if not os.path.exists(injector):
        warn(f'Injector not found: {injector}')
        log('Add SageAttention-T4 node manually or re-run the script')
        return

    workflows_dir = os.path.join(COMFY_DIR, 'user', 'default', 'workflows')
    if not os.path.isdir(workflows_dir):
        warn(f'Workflow folder not found: {workflows_dir}')
        log('Add SageAttention-T4 node manually or save workflow and re-run script')
        return

    run([sys.executable, injector, workflows_dir], check=False)


def main():
    step("STEP 2: custom nodes + model links")

    check_prerequisites()

    step("Installing custom nodes")
    for name, repo in CUSTOM_NODES.items():
        install_node(name, repo)

    step("Model symlinks")
    for src, dst in SYMLINKS:
        make_symlink(src, dst)

    log("DONE. Nodes and models in place. Now run: %run instal/start.py")
    # SageAttention-T4 workflow injection happens later in start.py (after symlink creation)


if __name__ == "__main__":
    main()
