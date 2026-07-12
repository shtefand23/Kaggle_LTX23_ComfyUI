#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
start.py
=================================================================
SINGLE ENTRY POINT for launching ComfyUI on Kaggle.

All in one: %run instal/start.py
  * checks what's missing
  * auto-installs ComfyUI / torch / custom nodes / models
  * launches ComfyUI + Cloudflare tunnel + SageAttention + keep-alive

No manual steps. One cell — full pipeline.

Architecture (all modules in instal/):
  * start.py           — thin entry (only setup_env + handoff to launcher)
  * kaggle_env.py      — paths, venv, uv (single source of truth)
  * launcher.py        — ComfyLauncher (checks, install, lifecycle)
  * logging_ui.py      — LogManager (UI + log throttling)
  * sage_installer.py  — SageAttention-SM75 (Turing T4)
=================================================================
"""

import importlib
import os
import shutil
import subprocess
import sys

# ----------------------------------------------------------------------
# 0. Determine instal/ root
# ----------------------------------------------------------------------
try:
    _KE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _KE_DIR = "/kaggle/working/instal"
sys.path.insert(0, _KE_DIR)

# ----------------------------------------------------------------------
# 1. git pull — update code from repository
#    Runs BEFORE cache cleanup so fresh files are already on disk.
# ----------------------------------------------------------------------
try:
    _r = subprocess.run(
        ["git", "-C", _KE_DIR, "pull", "--ff-only"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if _r.returncode == 0:
        _out = (_r.stdout + _r.stderr).strip()
        if "Already up to date" not in _out and "Already up-to-date" not in _out:
            print("⚙️ [start] git pull: code updated from repository")
    else:
        print(f"⚙️ [start] git pull: {_r.stderr.strip()[:120]}")
except Exception as _exc:
    print(f"⚙️ [start] git pull failed: {_exc}")

# ----------------------------------------------------------------------
# 2. Reset stale module cache and .pyc files
#    After git pull fresh files are on disk. We clear everything that
#    may have been cached in memory (sys.modules) and on disk (__pycache__).
# ----------------------------------------------------------------------

# 2a. Remove instal modules from memory — Python will re-read fresh .py files.
for _mod_name in list(sys.modules.keys()):
    if _mod_name in (
        "kaggle_env", "logging_ui", "launcher", "sage_installer",
        "instal_comfyui", "instal_castom_node",
    ):
        del sys.modules[_mod_name]

# 2b. Clean all __pycache__ recursively — stale .pyc survives git pull,
#     and Python may not recompile if timestamps match.
for _root, _dirs, _files in os.walk(_KE_DIR):
    if "__pycache__" in _dirs:
        shutil.rmtree(os.path.join(_root, "__pycache__"), ignore_errors=True)
        _dirs.remove("__pycache__")

# 2c. Invalidate importlib finder caches — so they re-read files
#     from disk instead of returning stale specs from internal cache.
importlib.invalidate_caches()

import kaggle_env as ke

# Set UV_* env variables and add /kaggle/working/bin to PATH.
# Without this `uv pip install` fails after Kaggle session restart.
ke.setup_env()


# ----------------------------------------------------------------------
# 2. Launch — all heavy work is in launcher.py
# ----------------------------------------------------------------------
def launch():
    """Hands off to ComfyLauncher. That will auto-install everything
    needed (ComfyUI, torch, nodes) and start the service."""
    os.chdir(ke.HOME_DIR)

    from launcher import ComfyLauncher
    return ComfyLauncher().launch()


# Launch automatically on `%run start.py`.
if __name__ == "__main__":
    launch()
