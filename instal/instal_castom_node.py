#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
instal_castom_node.py
=================================================================
STEP 2 of 3. Installs custom nodes and creates symlinks for models.

LTX 2.3 Director V2 Beta workspace:
  All 19 models from martasteiner/ltxdirector dataset.

Run (in notebook):  !python instal/instal_castom_node.py
=================================================================
"""

import os
import shutil
import subprocess
import sys

# Shared module next to file
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kaggle_env import (
    COMFY_DIR, NODES_DIR, VENV_PYTHON,
    log, warn, step, run,
    install_python,
)

# ----------------------------------------------------------------------
# CUSTOM NODE LIST  (name -> git repository).
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
    # ── Academia SD Downloader ──
    "ComfyUI-AcademiaSD": "https://github.com/ComfyUI-AcademiaSD/ComfyUI-AcademiaSD.git",
}

# ----------------------------------------------------------------------
# MODEL SYMLINKS  — uses /kaggle/temp/ltx23/ as staging area.
# Dataset: martasteiner/ltxdirector (all 19 models)
# ----------------------------------------------------------------------
DATASET_SRC = "/kaggle/input/datasets/martasteiner/ltxdirector"
TEMP_DIR    = "/kaggle/temp/ltx23"
MODELS_DIR  = os.path.join(TEMP_DIR, "models")

# All 19 model files: (subfolder, filename)
MODEL_FILES = [
    # ── Diffusion Models (1) ──
    ("diffusion_models", "ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors"),
    # ── GGUF Alternative (2) ──
    ("diffusion_models", "ltx-2.3-22b-distilled-1.1-UD-Q5_K_M.gguf"),
    # ── Text Encoders (3-4) ──
    ("text_encoders", "gemma_3_12B_it_fp8_scaled.safetensors"),
    ("text_encoders", "ltx-2.3_text_projection_bf16.safetensors"),
    # ── VAE (5-7) ──
    ("vae", "LTX23_video_vae_bf16.safetensors"),
    ("vae", "LTX23_audio_vae_bf16.safetensors"),
    ("vae", "taeltx2_3.safetensors"),
    # ── Upscaler (8) ──
    ("latent_upscale_models", "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"),
    # ── LoRAs (9-10) ──
    ("loras", "ltx-2.3-22b-distilled-1.1_lora-dynamic_fro09_avg_rank_111_bf16.safetensors"),
    ("loras", "LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors"),
    # ── IC LoRAs (11-19) ──
    ("loras", "ltx-2.3-22b-ic-lora-cross-eyed-0.9.safetensors"),
    ("loras", "ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors"),
    ("loras", "ltx-2-19b-ic-lora-detailer.safetensors"),
    ("loras", "lora_weights_step_12000.safetensors"),
    ("loras", "ltx2.3_upscale_ic-lora_06250.safetensors"),
    ("loras", "ltx-2.3-22b-ic-lora-lipdub-0.9.safetensors"),
    ("loras", "ltx2.3_audio_reactive_lora_v2.safetensors"),
    ("loras", "ltx-2.3-22b-ic-lora-hdr-0.9.safetensors"),
    ("loras", "ltx-2.3-22b-ic-lora-decompression-0.9.safetensors"),
]


def stage_models():
    """Copy models from dataset to /kaggle/temp/ (skips if already there)."""
    step("Stage models to /kaggle/temp/")
    if not os.path.isdir(DATASET_SRC):
        warn(f"Dataset not found at {DATASET_SRC} — add it to your Kaggle session")
        return
    all_cached = all(
        os.path.exists(os.path.join(MODELS_DIR, sf, fn))
        for sf, fn in MODEL_FILES
    )
    if all_cached:
        log("All models cached in /kaggle/temp/ — skipping copy")
        return
    for subfolder, filename in MODEL_FILES:
        src = os.path.join(DATASET_SRC, filename)
        dst = os.path.join(MODELS_DIR, subfolder, filename)
        if os.path.exists(dst):
            log(f"Cached: {filename}")
            continue
        if not os.path.exists(src):
            warn(f"Not in dataset: {filename}")
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        print(f"  Copying {filename} ...", end=" ", flush=True)
        shutil.copy2(src, dst)
        print("done")
    log("Models staged")


SYMLINKS = []
for subfolder, filename in MODEL_FILES:
    SYMLINKS.append((
        os.path.join(MODELS_DIR, subfolder, filename),
        os.path.join(COMFY_DIR, "models", subfolder, filename),
    ))


def uv_pip_install_req(req_path):
    """Installs node requirements into our venv via uv."""
    result = run(["uv", "pip", "install", "--python", VENV_PYTHON, "-r", req_path], check=False)
    if result and result.returncode != 0:
        warn(f"Failed to install node requirements: {req_path}")


def check_prerequisites():
    """Checks that STEP 1 is complete: uv exists, working venv, custom_nodes."""
    step("Checking environment (STEP 1 result)")
    install_python()
    if not os.path.exists(NODES_DIR):
        raise RuntimeError(
            f"Folder {NODES_DIR} not found. "
            "First run: !python instal/instal_comfyui.py"
        )
    log("Environment ready: uv, venv and ComfyUI in place")


def install_node(name, repo):
    target = os.path.join(NODES_DIR, name)
    if not os.path.exists(target):
        run(["git", "clone", repo, target])
    else:
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


def make_symlink(src, dst):
    if not os.path.exists(src):
        warn(f"Source not found, skipping: {src}")
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.islink(dst) or os.path.exists(dst):
        os.remove(dst)
    os.symlink(src, dst)
    log(f"Link: {os.path.basename(dst)}")


def copy_workflows():
    """Copy workflow JSON files into ComfyUI workflows folder."""
    step("Copying workflows")
    workflows_dst = os.path.join(COMFY_DIR, "user", "default", "workflows")
    os.makedirs(workflows_dst, exist_ok=True)

    # Source: repo workflows folder
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(repo_dir)
    workflows_src = os.path.join(repo_root, "workflows")

    if not os.path.isdir(workflows_src):
        warn(f"Workflows folder not found: {workflows_src}")
        return

    count = 0
    for fname in os.listdir(workflows_src):
        if fname.endswith(".json"):
            src = os.path.join(workflows_src, fname)
            dst = os.path.join(workflows_dst, fname)
            if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst):
                shutil.copy2(src, dst)
                log(f"Workflow: {fname}")
                count += 1
    log(f"Workflows: {count} copied to {workflows_dst}")


def main():
    step("STEP 2: custom nodes + model links + workflows")

    check_prerequisites()

    step("Installing custom nodes")
    for name, repo in CUSTOM_NODES.items():
        install_node(name, repo)

    step("Model symlinks")
    stage_models()
    for src, dst in SYMLINKS:
        make_symlink(src, dst)

    copy_workflows()

    log("DONE. Nodes, models and workflows in place. Now run: %run instal/start.py")


if __name__ == "__main__":
    main()
