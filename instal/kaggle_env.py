#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kaggle_env.py
=================================================================
SHARED MODULE (single source of truth) for all three installation steps
of ComfyUI on Kaggle: instal_comfyui.py, instal_castom_node.py, start.py.

Why it's needed
---------------
Previously the "paths + uv install + venv check + +x repair" logic was
DUPLICATED across three files with divergences. Those divergences broke
session restart survival on Kaggle. Now everything is in one place.

The key reliability idea: ALL uv state lives in /kaggle/working —
the only directory that survives Kaggle session restarts:

    UV_INSTALL_DIR        (uv binary itself)      -> /kaggle/working/bin
    UV_PYTHON_INSTALL_DIR (base CPython)          -> /kaggle/working/uv-python
    UV_CACHE_DIR          (wheels, incl. torch)    -> /kaggle/working/uv-cache
    venv                                            -> /kaggle/working/venv

After a Kaggle restart files remain in place but lose the execute bit
(+x). So the only needed repair is restoring +x (repair_venv_perms),
NOT reinstalling uv/torch from scratch.

KEY FIX: uv is installed via the UV_INSTALL_DIR environment variable.
Previously the `--bin-dir` flag was used, which the uv installer DOES
NOT HAVE — it was silently ignored, and uv ended up in ~/.local/bin
(NOT persistent), disappeared after restart, and everything had to be
reinstalled.
=================================================================
"""

import os
import shutil
import subprocess

# ----------------------------------------------------------------------
# Paths and parameters. Change here — picked up by all three scripts.
# ----------------------------------------------------------------------
HOME_DIR      = "/kaggle/working"
VENV_DIR      = f"{HOME_DIR}/venv"
VENV_PYTHON   = f"{VENV_DIR}/bin/python"
COMFY_DIR     = f"{HOME_DIR}/ComfyUI"
NODES_DIR     = f"{COMFY_DIR}/custom_nodes"

# Persistent uv directories (all in /kaggle/working — survive restart).
UV_LOCAL_DIR  = f"{HOME_DIR}/bin"        # uv binary itself (UV_INSTALL_DIR)
UV_PYTHON_DIR = f"{HOME_DIR}/uv-python"  # uv-managed base CPython
UV_CACHE_DIR  = f"{HOME_DIR}/uv-cache"   # wheel cache (torch won't re-download)

PYTHON_VERSION = "3.12"                   # interpreter version in venv

UV_INSTALL_URL = "https://astral.sh/uv/install.sh"


# ----------------------------------------------------------------------
# Unified output style (previously duplicated in each file).
# ----------------------------------------------------------------------
def log(msg):   print(f"\n\033[92m✅ {msg}\033[0m", flush=True)
def warn(msg):  print(f"\n\033[93m⚠️  {msg}\033[0m", flush=True)
def step(msg):  print(f"\n\033[96m=== {msg} ===\033[0m", flush=True)


def run(cmd, check=True, **kwargs):
    """Prints and executes a command. Fails by default on error."""
    if isinstance(cmd, str):
        printable = cmd
        kwargs.setdefault("shell", True)
    else:
        printable = " ".join(cmd)
        kwargs.setdefault("shell", False)
    print(f"$ {printable}", flush=True)
    return subprocess.run(cmd, check=check, **kwargs)


# ----------------------------------------------------------------------
# uv environment setup. Lightweight and safe to import — called
# automatically at module end so any importing script immediately
# gets the correct PATH and uv env variables.
# ----------------------------------------------------------------------
def setup_env():
    """Prepares uv environment: persistent directories + uv in PATH.

    No heavy work (downloads nothing) — safe to call any number of times.
    """
    # uv cache and venv on Kaggle are on different filesystems — hardlink
    # doesn't work, uv complains. copy mode removes the warning and
    # unnecessary linking attempts.
    os.environ.setdefault("UV_LINK_MODE", "copy")
    # uv shouldn't ask interactive questions (nobody to answer in a notebook).
    os.environ.setdefault("UV_NO_PROMPT", "1")
    # Base CPython and cache in persistent /kaggle/working directories.
    os.environ.setdefault("UV_PYTHON_INSTALL_DIR", UV_PYTHON_DIR)
    os.environ.setdefault("UV_CACHE_DIR", UV_CACHE_DIR)
    # Only use uv-managed python (not system one from ~ which will disappear).
    os.environ.setdefault("UV_PYTHON_PREFERENCE", "only-managed")

    # Create directories in advance (tolerant of errors for local import outside Kaggle).
    for d in (UV_LOCAL_DIR, UV_CACHE_DIR):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass

    # Persistent uv directory at the front of PATH (may have dropped after restart).
    # THIS is what was missing in start.py: its `uv pip install` failed after restart.
    if os.path.isdir(UV_LOCAL_DIR) and UV_LOCAL_DIR not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = UV_LOCAL_DIR + os.pathsep + os.environ.get("PATH", "")


# ----------------------------------------------------------------------
# uv installation. Idempotent: installs only if missing, and fixes +x.
# ----------------------------------------------------------------------
def ensure_uv():
    """Guarantees a working uv in the persistent directory.

    We use the standalone installer (curl), NOT pip — because:
      1) system Python on Kaggle is "externally managed" (PEP 668), pip fails;
      2) pip installs uv to ~/.local/bin — NOT persistent, disappears after restart.

    The installer places the binary in UV_INSTALL_DIR=/kaggle/working/bin (persistent).
    """
    setup_env()

    # Already in PATH and working — exit.
    if shutil.which("uv"):
        log("uv already installed (skipping)")
        return

    # Binary exists on disk but lost +x after Kaggle restart — cheap fix.
    uv_bin = os.path.join(UV_LOCAL_DIR, "uv")
    if os.path.exists(uv_bin):
        warn("uv found but without +x bit (Kaggle restart removed it) — restoring +x")
        try:
            os.chmod(uv_bin, 0o755)
        except OSError:
            pass
        os.environ["PATH"] = UV_LOCAL_DIR + os.pathsep + os.environ.get("PATH", "")
        if shutil.which("uv"):
            log("uv repaired by restoring +x")
            return

    step("Installing uv (standalone → /kaggle/working/bin)")
    os.makedirs(UV_LOCAL_DIR, exist_ok=True)
    installer = os.path.join(UV_LOCAL_DIR, "uv-install.sh")
    run(["curl", "-LsSf", UV_INSTALL_URL, "-o", installer])
    # KEY FIX: directory is set via UV_INSTALL_DIR env variable, NOT the
    # --bin-dir flag (which the installer DOESN'T HAVE). UV_NO_MODIFY_PATH=1
    # — don't touch shell profiles (we don't need that, we fix PATH ourselves
    # via setup_env).
    env = dict(os.environ)
    env["UV_INSTALL_DIR"] = UV_LOCAL_DIR
    env["UV_NO_MODIFY_PATH"] = "1"
    run(["sh", installer], env=env)

    os.environ["PATH"] = UV_LOCAL_DIR + os.pathsep + os.environ.get("PATH", "")
    if not shutil.which("uv"):
        raise RuntimeError("Failed to install uv — check the log above")
    log("uv installed to persistent directory /kaggle/working/bin")


# ----------------------------------------------------------------------
# venv check and repair.
# ----------------------------------------------------------------------
def venv_python_ok():
    """venv is considered working only if its python ACTUALLY launches.

    /kaggle/working/venv survives session restarts, but the +x bit on
    the interpreter and base CPython gets reset → symlink is intact but
    not executable. So we check by actually running, not os.path.exists.
    """
    if not os.path.exists(VENV_PYTHON):
        return False
    try:
        subprocess.run([VENV_PYTHON, "-c", "pass"],
                       check=True, capture_output=True, timeout=30)
        return True
    except subprocess.TimeoutExpired:
        return False
    except (subprocess.SubprocessError, OSError) as exc:
        # Catch stderr if binary exists but fails (libc, kernel, ...)
        try:
            err = subprocess.run(
                [VENV_PYTHON, "-c", "pass"],
                capture_output=True, timeout=15
            )
            detail = (err.stderr or b"").decode("utf-8", errors="replace")[:500]
        except Exception as e2:
            detail = str(e2)[:500]
        warn(f"venv python exists but DOES NOT LAUNCH: {detail}")
        return False


def diagnose_venv():
    """Explains in detail WHY venv won't launch (for the log after restart)."""
    p = VENV_PYTHON
    if not os.path.lexists(p):
        return "venv/bin/python DOES NOT EXIST (venv folder not created or deleted)"
    if os.path.islink(p):
        target = os.path.realpath(p)
        if not os.path.exists(target):
            return (f"venv/bin/python is a BROKEN SYMLINK to {os.readlink(p)} "
                    f"(base CPython didn't survive session restart)")
        if not os.access(target, os.X_OK):
            return (f"base CPython exists ({target}) but WITHOUT +x bit "
                    f"(Kaggle restart removed execute permission)")
    elif not os.access(p, os.X_OK):
        return "venv/bin/python exists but WITHOUT +x bit (restart removed execute)"
    return "python is in place and executable but fails on launch (see error below)"


def repair_venv_perms():
    """Cheaply fixes the most common post-restart failure: lost +x bit.

    Returns True if venv works after repair. Does not recreate venv and
    doesn't touch torch — saves minutes on every startup.
    """
    candidates = []
    if os.path.lexists(VENV_PYTHON):
        candidates.append(VENV_PYTHON)
        real = os.path.realpath(VENV_PYTHON)
        if real != VENV_PYTHON:
            candidates.append(real)
    # uv binary in persistent directory also loses +x after restart.
    uv_bin = os.path.join(UV_LOCAL_DIR, "uv")
    if os.path.exists(uv_bin):
        candidates.append(uv_bin)
    # All executable python in persistent uv-CPython directory.
    if os.path.isdir(UV_PYTHON_DIR):
        for root, _dirs, files in os.walk(UV_PYTHON_DIR):
            for f in files:
                if f == "python3" or f.startswith("python3."):
                    candidates.append(os.path.join(root, f))
    fixed = False
    for c in candidates:
        try:
            if os.path.exists(c):
                os.chmod(c, 0o755)
                fixed = True
        except OSError:
            pass
    if fixed:
        warn("Restored +x bit to venv/uv-python interpreter (lost after restart)")
    return venv_python_ok()


def repair_base_python_via_uv():
    """If base CPython is broken (libc/kernel), removes old and installs fresh.

    IMPORTANT: this function does NOT fix venv — old venv points to old
    binary (different path). It only prepares a WORKING base CPython
    so the next `uv venv --clear` creates a venv with new CPython.
    Packages will be reinstalled from uv cache (fast, torch already downloaded).

    Returns:
      True  — base CPython reinstalled, ready to recreate venv;
      False — uv couldn't install CPython (need to reinstall uv).
    """
    # 1. Remove old CPython — uv will know it needs to install fresh
    #    (without this uv says "already installed" and skips).
    if os.path.isdir(UV_PYTHON_DIR):
        warn(f"Removing old base CPython: {UV_PYTHON_DIR}")
        shutil.rmtree(UV_PYTHON_DIR, ignore_errors=True)

    # 2. Make sure uv is in PATH (may have disappeared after restart).
    ensure_uv()

    # 3. Install fresh CPython for current Kaggle kernel.
    warn("Installing fresh base CPython via uv python install...")
    result = run(["uv", "python", "install", PYTHON_VERSION], check=False)
    if result.returncode != 0:
        warn(f"uv python install failed (code {result.returncode}) — "
             f"full reinstall needed")
        return False

    # 4. Check that fresh python works (just in case).
    #    Look for any python3.12 in UV_PYTHON_DIR (uv may have installed new one).
    fresh_python = None
    if os.path.isdir(UV_PYTHON_DIR):
        for root, _dirs, files in os.walk(UV_PYTHON_DIR):
            for f in files:
                if f.startswith("python3.12"):
                    fp = os.path.join(root, f)
                    try:
                        subprocess.run([fp, "-c", "pass"],
                                       check=True, capture_output=True, timeout=15)
                        fresh_python = fp
                        break
                    except (subprocess.SubprocessError, OSError):
                        continue
            if fresh_python:
                break

    if fresh_python:
        warn(f"Fresh CPython works: {fresh_python}. "
             f"Now a new venv is needed (will be created automatically).")
        return True

    warn("Could not find working CPython after uv python install")
    return False


def ensure_venv():
    """Guarantees a working venv. Idempotent and maximally cheap.

    Logic by increasing cost:
      1) venv already works                       → do nothing;
      2) folder exists but broken → fix +x        → don't touch torch;
      3) +x didn't help → reinstall CPython via uv
         (prepare for venv recreation, packages from uv cache);
      4) everything is bad / no venv → recreate    → uv venv (+seed).

    Returns:
      True  — venv was already working (did nothing);
      False — venv was repaired/recreated (torch and packages may be gone).
    """
    step("Checking/creating venv")
    if venv_python_ok():
        log(f"venv already exists and works: {VENV_DIR} (recreation skipped)")
        return True

    if os.path.exists(VENV_DIR):
        warn(f"venv found but not working. Reason: {diagnose_venv()}")
        # Stage 2: cheaply fix +x (common failure after Kaggle restart).
        if repair_venv_perms():
            log(f"venv repaired by restoring +x — recreation and torch "
                f"reinstall NOT needed: {VENV_DIR}")
            return False
        # Stage 3: +x didn't help — maybe Kaggle updated the kernel and old
        # CPython is incompatible with libc. Remove it and install fresh.
        warn(f"+x didn't help — trying to reinstall base CPython: {VENV_DIR}")
        repair_base_python_via_uv()
        # NB: repair_base_python_via_uv does NOT fix venv (old symlink
        # points to deleted CPython). It only prepares fresh CPython
        # for the next step. Continue with venv recreation.

    ensure_uv()  # need uv for recreation
    # --seed puts pip/setuptools inside venv — some nodes need this.
    # --quietly overwrites existing folder (no "clear?" prompt).
    run(["uv", "venv", VENV_DIR, "--python", PYTHON_VERSION, "--seed", "--clear"])
    if not venv_python_ok():
        raise RuntimeError("venv created but python won't launch — see log above")
    log(f"venv created on Python {PYTHON_VERSION}: {VENV_DIR}")
    return False


def torch_cuda_ok():
    """Checks that torch is installed in venv and sees CUDA.

    Used after recreating venv or after an interrupted install,
    to not miss reinstalling if torch is broken/missing.
    """
    if not venv_python_ok():
        return False
    try:
        subprocess.run(
            [VENV_PYTHON, "-c", "import torch; assert torch.cuda.is_available()"],
            check=True, capture_output=True, timeout=120)
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def install_python():
    """Guarantees a working Python: uv in PATH + venv (created/repaired/recreated).

    Single entry point for all three scripts (instal_comfyui.py,
    instal_castom_node.py, start.py). Internally calls:
       1. ensure_uv()   — installs uv binary (if missing / broken),
       2. ensure_venv() — checks venv, fixes +x, reinstalls CPython,
                          recreates venv if needed.

    Idempotent and maximally cheap: if everything already works — does nothing.

    Returns:
      True  — all components were already working (did nothing);
      False — repair/recreation was performed (packages may be gone).
    """
    ensure_uv()
    return ensure_venv()


def uv_pip_install(*packages, extra_args=None):
    """uv pip install into our venv (faster than regular pip)."""
    cmd = ["uv", "pip", "install", "--python", VENV_PYTHON]
    if extra_args:
        cmd += list(extra_args)
    cmd += list(packages)
    run(cmd)


# Set up environment on import — any script that imported the module
# gets correct PATH and uv env variables without extra calls.
setup_env()
