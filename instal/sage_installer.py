#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sage_installer.py
=================================================================
Installation of SageAttention-SM75-path (Turing T4, sm_75) + injection
of SageAttentionT4_Apply node into workflow.

Extracted from start.py to keep start.py thin.

Uses LogManager (logging_ui.py) for output — logs go into the
beautiful start.py wrapper.

Fork: https://github.com/THE-ANGEL-AI/SageAttention-SM75-path.git
Turing (sm_75) support via CUDA kernel sageattn_qk_int8_pv_fp16_cuda_sm75.
=================================================================
"""

import os
import subprocess
import sys

# Path to SageAttention repository (relative to HOME_DIR)
SAGE_SRC_DIR = "sageattention-sm75"

# Fork with Turing (sm_75) support
SAGE_REPO = "https://github.com/THE-ANGEL-AI/SageAttention-SM75-path.git"


def _run(cmd, **kwargs):
    """Prints and executes a command, returns result."""
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("timeout", 120)
    print(f"  $ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    return subprocess.run(cmd, **kwargs)


def install(home_dir, venv_python, comfy_dir, logger):
    """Builds SageAttention-SM75 in venv and links custom_node.

    Parameters:
      home_dir     — /kaggle/working
      venv_python  — path to python in venv
      comfy_dir    — path to ComfyUI (for custom_nodes symlink)
      logger       — LogManager instance (from logging_ui.py)

    Returns:
      True if SageAttention is installed and ready to use.
    """
    logger.set_status("⚙️ Checking SageAttention-SM75 (Turing)...", "#f39c12")
    sage_ok = False
    sage_src = os.path.join(home_dir, SAGE_SRC_DIR)

    # --- Step 0: already installed? ---
    logger.print("[*] Checking SageAttention-SM75 (Turing)...")
    check = subprocess.run(
        [venv_python, "-c", "import sageattention"],
        capture_output=True, text=True, timeout=15)
    if check.returncode == 0:
        logger.print("[*] SageAttention already installed (skipping)")
        return True

    # --- Step 1: build dependencies ---
    logger.set_status("⚙️ Installing SageAttention-SM75...", "#f39c12")
    logger.print("[*] Updating setuptools + wheel...")
    subprocess.run(
        [venv_python, "-m", "pip", "install", "--upgrade",
         "setuptools", "wheel"],
        capture_output=True, text=True, timeout=120)

    # --- Step 2: clone/update repository ---
    if os.path.isdir(sage_src):
        _ensure_fork_remote(sage_src, logger)
        _update_repo(sage_src, logger)
    else:
        _clone_repo(sage_src, logger)

    if not os.path.isdir(sage_src):
        logger.print("[!] SageAttention repository not available — skipping")
        return False

    # --- Step 3: build CUDA extension ---
    logger.print("[*] Compiling CUDA kernel for sm_75 (this may take 5-10 min)...")
    result = subprocess.run(
        [venv_python, "setup.py", "build_ext", "--inplace"],
        cwd=sage_src,
        capture_output=True, text=True, timeout=900)

    # Save full build log
    _save_build_log(sage_src, result, logger)

    # --- Step 4: analyze build result ---
    if result.returncode != 0:
        _log_build_failure(result, logger)
        return False

    # --- Step 5: install package ---
    sage_ok = _install_package(sage_src, venv_python, logger)
    if not sage_ok:
        logger.print("[!] Fallback: split-cross-attention (without SageAttention)")
        return False

    # --- Step 6: symlink into custom_nodes ---
    _link_custom_node(sage_src, comfy_dir, logger)

    logger.print("[OK] SageAttention-SM75 ready!")
    return True


def _ensure_fork_remote(sage_src, logger):
    """Switch remote origin to fork (if previously cloned XUANNISSAN)."""
    subprocess.run(
        ["git", "-C", sage_src, "remote", "set-url", "origin", SAGE_REPO],
        capture_output=True, text=True, timeout=30)
    logger.print("[*] Repository already cloned — checking for fork updates...")


def _update_repo(sage_src, logger):
    """Resets local patches and does pull."""
    subprocess.run(
        ["git", "-C", sage_src, "reset", "--hard", "--quiet"],
        capture_output=True, text=True, timeout=30)
    subprocess.run(
        ["git", "-C", sage_src, "fetch", "--quiet"],
        capture_output=True, text=True, timeout=30)
    pull = subprocess.run(
        ["git", "-C", sage_src, "pull", "--ff-only"],
        capture_output=True, text=True, timeout=60)
    if pull.returncode == 0:
        out = (pull.stdout or "").strip()
        if out and "Already up to date" not in out:
            logger.print(f"[*] Fork updated: {out.splitlines()[-3:][0]}")
        else:
            logger.print("[*] Fork up to date")
    else:
        err = (pull.stderr or "").strip()[:200]
        logger.print(f"[!] git pull failed: {err} (old version)")


def _clone_repo(sage_src, logger):
    """Clones the SageAttention fork."""
    logger.print("[*] Cloning SageAttention-SM75-path (fork)...")
    clone = subprocess.run(
        ["git", "clone", SAGE_REPO, sage_src],
        capture_output=True, text=True, timeout=120)
    if clone.returncode != 0:
        err = (clone.stderr or "").strip()[:200]
        logger.print(f"[!] Clone failed: {err}")


def _save_build_log(sage_src, result, logger):
    """Saves build log to file."""
    log_text = (result.stdout or "").strip()
    err_text = (result.stderr or "").strip()
    log_path = os.path.join(sage_src, "build_sm75.log")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("=== STDOUT ===\n" + log_text + "\n=== STDERR ===\n" + err_text)
        logger.print(f"[*] Full log saved to {log_path}")
    except OSError:
        pass

    # Parse compilation errors
    full = log_text + "\n" + err_text
    lines = full.split("\n")
    traceback_start = -1
    for i, l in enumerate(lines):
        if 'File "/kaggle/' in l and 'python' in l.lower():
            traceback_start = i
            break

    if traceback_start > 0:
        compile_lines = lines[:traceback_start]
        logger.print(f"[*] Lines before traceback: {len(compile_lines)}")
        err_lines = [
            l for l in compile_lines
            if any(x in l.lower() for x in [
                "error:", "fatal", "undefined", "no member", "not declared",
                "implicit", "failed:", "ninja: build stopped",
                "cannot find", "no such file",
            ])
        ]
        if err_lines:
            logger.print("[!] COMPILATION/BUILD ERRORS:")
            for line in err_lines[-40:]:
                logger.print(f"  ⛔ {line}")
            return True  # errors found
        logger.print("[*] Last compilation lines (before traceback):")
        for line in compile_lines[-50:]:
            logger.print(f"  {line}")
    else:
        logger.print("[*] Traceback not found, last log lines:")
        for line in lines[-30:]:
            logger.print(f"  {line}")
    return False


def _log_build_failure(result, logger):
    """Prints build error information."""
    logger.print(f"[!] Build failed (code {result.returncode})")
    logger.print("[!] Falling back to split-cross-attention (without Sage)")
    logger.set_status("⚠️ SageAttention not installed — running without acceleration", "#f39c12")


def _install_package(sage_src, venv_python, logger):
    """Installs the built package into venv."""
    logger.print("[*] CUDA kernel compiled, installing package...")
    install = subprocess.run(
        [venv_python, "-m", "pip", "install", "--no-build-isolation",
         "--no-deps", "."],
        cwd=sage_src,
        capture_output=True, text=True, timeout=120)
    for line in (install.stdout or "").split("\n")[-10:]:
        logger.print(f"  {line}")

    verify = subprocess.run(
        [venv_python, "-c", "import sageattention"],
        capture_output=True, text=True, timeout=15)
    if verify.returncode == 0:
        logger.print("[OK] SageAttention-SM75 installed!")
        return True

    logger.print(f"[!] Package installed but won't import: "
                 f"{verify.stderr.strip()[:200]}")
    return False


def _link_custom_node(sage_src, comfy_dir, logger):
    """Creates SageAttention-T4 symlink in custom_nodes."""
    sage_node_dir = os.path.join(comfy_dir, "custom_nodes", "SageAttention-T4")
    try:
        if os.path.islink(sage_node_dir):
            if os.readlink(sage_node_dir) != sage_src:
                os.unlink(sage_node_dir)
                os.symlink(sage_src, sage_node_dir)
                logger.print("[*] ComfyUI node symlink updated: SageAttention-T4")
            else:
                logger.print("[*] ComfyUI node already in custom_nodes: SageAttention-T4")
        elif not os.path.exists(sage_node_dir):
            os.symlink(sage_src, sage_node_dir)
            logger.print("[*] ComfyUI node symlink created: SageAttention-T4")
        else:
            logger.print(f"[*] ComfyUI node dir exists: {sage_node_dir}")
    except OSError as e:
        logger.print(f"[!] Symlink failed ({e}) — node won't be detected")


def inject_into_workflows(comfy_dir, logger):
    """Injects SageAttentionT4_Apply into workflow JSON.

    Calls scripts/inject_sageattn_workflow.py for all .json files
    in ComfyUI/user/default/workflows/.
    """
    # Path to injector — in scripts/ next to this file
    injector = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "scripts", "inject_sageattn_workflow.py"
    )
    if not os.path.exists(injector):
        logger.print(f"[!] Injector not found: {injector}")
        return

    workflows_dir = os.path.join(comfy_dir, "user", "default", "workflows")
    if not os.path.isdir(workflows_dir):
        logger.print(f"[!] Workflow folder not found: {workflows_dir}")
        logger.print("[*] SageAttention injection skipped — save workflow and re-run")
        return

    logger.print("[*] Injecting SageAttention-T4 into workflow...")
    subprocess.run(
        [sys.executable, injector, workflows_dir],
        check=False)
    logger.print("[*] Injection complete")
