#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
launcher.py
=================================================================
Main ComfyUI orchestrator on Kaggle.

Contains ComfyLauncher — a class managing the lifecycle:
  1. Environment check and repair (venv, torch, nodes)
  2. Cloudflared tunnel
  3. ComfyUI launch + port wait
  4. Keep-alive (anti-sleep) + HTML panel

Paths — ONLY from kaggle_env (single source of truth).
UI and logs — via LogManager (logging_ui.py).
Widgets: widgets.HTML for log, status, heartbeat, URL.
Buttons: widgets.Button for stop and restart.
Stop — the "🛑 Stop" button in the panel.
=================================================================
"""

import os
import re
import socket
import subprocess
import sys
import time
import traceback
from datetime import datetime
from threading import Event, Thread

# Shared module — single source of paths
import kaggle_env as ke
from kaggle_env import (
    HOME_DIR, COMFY_DIR, VENV_PYTHON,
)

# UI + logs
from logging_ui import LogManager

# SageAttention-SM75 (Turing T4) — build + custom node
import sage_installer



# Path to installer scripts
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
INSTALLER      = os.path.join(_THIS_DIR, "instal_comfyui.py")
NODE_INSTALLER = os.path.join(_THIS_DIR, "instal_castom_node.py")

# Timeouts
PORT            = 8188
STARTUP_TIMEOUT = 240   # seconds for ComfyUI launch
URL_TIMEOUT     = 90    # seconds to get Cloudflare link
CLOUDFLARED     = f"{HOME_DIR}/cloudflared"

# Auto-update nodes
AUTO_UPDATE_NODES = True


class ComfyLauncher:
    """Holds processes and the entire launch/stop lifecycle."""

    def __init__(self):
        self.comfy_proc = None
        self.tunnel_proc = None
        self.public_url = None
        self.stopped = False
        self._starting = False
        self.sage_ok = False
        # UI + logs
        self.logger = LogManager()
        self.logger.on_stop_callback = self._on_stop
        self.logger.on_restart_callback = self._on_restart

    # ------------------------------------------------------------------
    # Console logging helpers
    # ------------------------------------------------------------------

    def _log_step(self, name, status=None):
        """Marks the start of a step: separator + timer + status.
        Returns time.time() for duration measurement."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.logger.print(f"\n{'='*60}")
        self.logger.print(f"  [{ts}] {name}")
        self.logger.print(f"{'='*60}")
        if status:
            self.logger.set_status(status, "#f39c12")
        return time.time()

    def _log_elapsed(self, start, msg="✓ Step complete"):
        """Logs time elapsed since start."""
        elapsed = time.time() - start
        self.logger.print(f"[{msg}] ({elapsed:.1f}s)")

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def launch(self):
        # Panel is drawn in LogManager.__init__ via display()
        Thread(target=self.logger._heartbeat_loop, daemon=True).start()
        Thread(target=self.logger._stdout_keep_alive, daemon=True).start()
        Thread(target=self._startup, daemon=True).start()

        self._keep_alive()

    # ------------------------------------------------------------------
    # Startup (in background thread)
    # ------------------------------------------------------------------
    def _startup(self):
        self._starting = True
        _t_startup = time.time()

        self.logger.print(f"\n{'='*60}")
        self.logger.print(f"  ComfyUI Launcher · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.print(f"{'='*60}")
        try:
            self._cleanup_old()
            self._check_git_updates()
            self._check_files()
            self._ensure_cloudflared()
            # SageAttention-SM75 is skipped — it DOES NOT work with GGUF models
            # (llama.cpp backend, not diffusion attention).
            # Generation speed is through ComfyUI/GGUF node settings.
            self._start_comfy()
            self._wait_for_port()
            self._start_tunnel()
            total = time.time() - _t_startup
            self.logger.print(f"\n{'='*60}")
            self.logger.print(f"  ✅ Full startup in {total:.1f}s")
            self.logger.print(f"{'='*60}")
        except Exception as e:
            self._kill_processes()
            self.logger.set_status(f"❌ Startup error: {e}", "#e74c3c")
            elapsed = time.time() - _t_startup
            self.logger.print(f"\n{'='*60}")
            self.logger.print(f"  ❌ Error at {elapsed:.0f}s: {e}")
            self.logger.print(f"{'='*60}")
            self.logger.print(f"[ERROR] {e}\n{traceback.format_exc()}")
        finally:
            self._starting = False

    # ------------------------------------------------------------------
    # 1. Kill old processes and clean up locks
    # ------------------------------------------------------------------
    def _cleanup_old(self):
        t0 = self._log_step("Step 1/6: Cleaning up old processes and locks")
        total_killed = 0
        for pat in ("main.py", "comfyui", "cloudflared"):
            try:
                pgrep = subprocess.run(
                    ["pgrep", "-f", pat],
                    capture_output=True, text=True)
                if pgrep.returncode == 0 and pgrep.stdout.strip():
                    pids = pgrep.stdout.strip().splitlines()
                    self.logger.print(f"  → {pat}: found PIDs: {', '.join(pids)}")
                    total_killed += len(pids)
                subprocess.run(["pkill", "-9", "-f", pat],
                               capture_output=True)
            except OSError:
                pass
        if total_killed == 0:
            self.logger.print("  → No old processes found")
        else:
            self.logger.print(f"  → Killed {total_killed} processes")
        time.sleep(2)
        removed = 0
        for f in (f"{COMFY_DIR}/user/comfyui.db",
                  f"{COMFY_DIR}/user/comfyui.db-journal"):
            try:
                if os.path.exists(f):
                    os.remove(f)
                    self.logger.print(f"  → Removed file: {os.path.basename(f)}")
                    removed += 1
            except OSError as e:
                self.logger.print(f"  → Could not remove {os.path.basename(f)}: {e}")
        if removed == 0:
            self.logger.print("  → No lock files found")
        self._log_elapsed(t0)

    # ------------------------------------------------------------------
    # 1b. Check for git repo updates
    # ------------------------------------------------------------------
    def _check_git_updates(self):
        t0 = self._log_step("Step 2/6: Checking for script updates (git)")

        try:
            result = subprocess.run(
                ["git", "-C", _THIS_DIR, "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=10, check=True)
            repo_root = result.stdout.strip()
        except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
            self.logger.print("  → Not a git clone — skipping")
            self._log_elapsed(t0)
            return

        try:
            # Current position
            branch = subprocess.run(["git", "-C", repo_root, "rev-parse",
                                     "--abbrev-ref", "HEAD"],
                                    capture_output=True, text=True, timeout=5)
            commit = subprocess.run(["git", "-C", repo_root, "rev-parse",
                                     "--short", "HEAD"],
                                    capture_output=True, text=True, timeout=5)
            self.logger.print(f"  → Branch: {branch.stdout.strip()}")
            self.logger.print(f"  → Commit: {commit.stdout.strip()}")

            # GIT_TERMINAL_PROMPT=0 — don't wait for interactive input
            fetch_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
            self.logger.print("  → Fetch...")
            fetch = subprocess.run(
                ["git", "-C", repo_root, "fetch", "--quiet"],
                capture_output=True, text=True, timeout=30,
                env=fetch_env)
            if fetch.returncode != 0:
                self.logger.print(f"  → git fetch: {fetch.stderr.strip()}")
                self._log_elapsed(t0)
                return

            status = subprocess.run(
                ["git", "-C", repo_root, "status", "-sb"],
                capture_output=True, text=True, timeout=15)
            behind = "behind" in (status.stdout + status.stderr)

            if not behind:
                self.logger.print("  → Up to date, no updates found")
                self.logger.set_status("✅ Scripts updated", "#27ae60")
                self._log_elapsed(t0)
                return

            self.logger.print("  → Found new commits — git pull...")
            self.logger.set_status("⚙️ Downloading updates...", "#f39c12")
            pull = subprocess.run(
                ["git", "-C", repo_root, "pull", "--ff-only"],
                capture_output=True, text=True, timeout=30)
            if pull.returncode != 0:
                self.logger.print(f"  → git pull: {pull.stderr.strip()}")
                self._log_elapsed(t0)
                return

            log = subprocess.run(
                ["git", "-C", repo_root, "log", "--oneline", f"{commit.stdout.strip()}..HEAD"],
                capture_output=True, text=True, timeout=5)
            n = len([l for l in log.stdout.splitlines() if l.strip()])
            self.logger.print(f"  → Downloaded {n} new commits")
            self.logger.set_status("✅ Scripts updated", "#27ae60")
        except subprocess.TimeoutExpired:
            self.logger.print("  → Git operation timeout — skipping")
        except Exception as e:
            self.logger.print(f"  → Error: {e}")
        self._log_elapsed(t0)

    # ------------------------------------------------------------------
    # 2. Check files and environment
    # ------------------------------------------------------------------
    def _check_files(self):
        t0 = self._log_step("Step 3/6: Checking files and environment")

        # --- venv ---
        self.logger.print("  ── Checking Python environment ──")
        if not ke.venv_python_ok():
            self.logger.print("  ❌ venv broken — running install_python()")
            try:
                was_ok = ke.install_python()
            except Exception as exc:
                self.logger.print(f"  ❌ install_python() failed: {exc}")
                raise RuntimeError(
                    "Error during Python environment installation") from exc
            if not ke.venv_python_ok():
                raise RuntimeError("venv didn't start working — see log above")
            self.logger.print("  ✅ venv restored")
            if not was_ok:
                self.logger.print("  → venv recreated — installing torch")
                self.logger.stream_script(INSTALLER, "INSTALL",
                    "Run manually: !python instal/instal_comfyui.py")
                self.logger.print("  → Reinstalling custom node dependencies")
                self.logger.stream_script(NODE_INSTALLER, "NODES",
                    "Run manually: !python instal/instal_castom_node.py")
        else:
            self.logger.print("  ✅ venv OK")

        # --- ComfyUI ---
        self.logger.print("  ── Checking ComfyUI ──")
        if not os.path.exists(f"{COMFY_DIR}/main.py"):
            self.logger.print("  ❌ ComfyUI not found — auto-installing")
            self.logger.stream_script(INSTALLER, "INSTALL",
                "Run manually: !python instal/instal_comfyui.py")
            self.logger.print("  ✅ ComfyUI installed")
        else:
            self.logger.print("  ✅ ComfyUI in place")

        # --- torch / CUDA ---
        self.logger.print("  ── Checking torch/CUDA ──")
        if not ke.torch_cuda_ok():
            self.logger.print("  ❌ torch doesn't see CUDA — reinstalling")
            self.logger.stream_script(INSTALLER, "INSTALL",
                "Run manually: !python instal/instal_comfyui.py")
            self.logger.print("  → Reinstalling node dependencies")
            self.logger.stream_script(NODE_INSTALLER, "NODES",
                "Run manually: !python instal/instal_castom_node.py")
        else:
            self.logger.print("  ✅ torch/CUDA OK")

        # --- Custom nodes (may pull pynvml via requirements.txt) ---
        self._check_nodes()
        # --- Model symlinks (always, regardless of node state) ---
        self._ensure_symlinks()
        # --- nvidia-ml-py (FINAL after all installs — remove pynvml redirect) ---
        self._ensure_nvidia_ml_py()
        self._log_elapsed(t0)

    # --- 2b. check and auto-update custom nodes ---
    def _load_node_names(self):
        """Node names from instal_castom_node.py (single source of truth)."""
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "instal_castom_node", NODE_INSTALLER)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return list(getattr(mod, "CUSTOM_NODES", {}).keys())
        except Exception as e:
            self.logger.print(f"[!] Could not read node list ({e}) — skipping check")
            return None

    def _update_node(self, name, path):
        """git pull one node + reinstall its requirements.txt in venv.

        Always reinstalls requirements.txt after pull — `uv pip install`
        is idempotent and fast on Already up to date. This guarantees
        node dependencies aren't lost after venv recreation.
        """
        # Force remote URL change if fork moved
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "instal_castom_node", NODE_INSTALLER)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            nodes = getattr(mod, "CUSTOM_NODES", {})
            expected_url = nodes.get(name)
            if expected_url:
                cur = subprocess.run(
                    ["git", "-C", path, "remote", "get-url", "origin"],
                    capture_output=True, text=True).stdout.strip()
                if cur != expected_url:
                    self.logger.print(
                        f"[NODES] {name}: remote URL changed: {cur} → {expected_url}")
                    subprocess.run(
                        ["git", "-C", path, "remote", "set-url", "origin", expected_url],
                        capture_output=True, text=True)
        except Exception as e:
            self.logger.print(f"[NODES] {name}: could not check remote URL ({e})")

        res = subprocess.run(
            ["git", "-C", path, "pull", "--ff-only"],
            capture_output=True, text=True)
        out = (res.stdout + res.stderr).strip()
        if res.returncode != 0:
            self.logger.print(f"[NODES] {name}: git pull failed, skipping — "
                        f"{out.splitlines()[-1] if out else 'no output'}")
            return
        if "Already up to date" not in out and "Already up-to-date" not in out:
            self.logger.print(f"[NODES] {name}: code updated ↓")
        # Always reinstall requirements — if venv was recreated,
        # packages are gone, and `uv pip install` is idempotent.
        req = os.path.join(path, "requirements.txt")
        if os.path.exists(req):
            subprocess.run(
                ["uv", "pip", "install", "--python", VENV_PYTHON, "-r", req],
                capture_output=True, text=True)

    def _update_existing_nodes(self, names):
        """Updates (git pull) all nodes from the list that are already on disk."""
        nodes_root = f"{COMFY_DIR}/custom_nodes"
        present = [(n, os.path.join(nodes_root, n)) for n in names
                   if os.path.isdir(os.path.join(nodes_root, n))]
        if not present:
            return
        self.logger.set_status("🔄 Updating custom nodes...", "#f39c12")
        self.logger.print(f"[*] Auto-updating nodes (git pull): {len(present)} items")
        for name, path in present:
            try:
                self._update_node(name, path)
            except Exception as e:
                self.logger.print(f"[NODES] {name}: update error ({e}), skipping")
        self.logger.print("[*] Node update complete")

    def _check_nodes(self):
        if not os.path.exists(NODE_INSTALLER):
            self.logger.print("[!] instal_castom_node.py not found — skipping nodes")
            return
        names = self._load_node_names()
        if names is None:
            return
        nodes_root = f"{COMFY_DIR}/custom_nodes"
        missing = [n for n in names
                   if not os.path.exists(os.path.join(nodes_root, n))]

        if missing:
            self.logger.set_status(
                f"⚙️ Installing missing custom nodes ({len(missing)})...", "#f39c12")
            self.logger.print(f"[!] Missing nodes: {', '.join(missing)} — auto-installing")
            self.logger.stream_script(NODE_INSTALLER, "NODES",
                "Run manually: !python instal/instal_castom_node.py")
            self.logger.print("[*] Custom nodes installed and updated")
            return

        if AUTO_UPDATE_NODES:
            self._update_existing_nodes(names)
        else:
            self.logger.print("[*] Custom nodes in place (auto-update disabled)")

    def _ensure_symlinks(self):
        """Creates model symlinks from SYMLINKS.

        Called always, regardless of node state. Links may not have
        been created on first install, may have disappeared after a
        Kaggle restart, or may have changed in the dataset.
        """
        self.logger.print("  ── Model symlinks ──")
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "instal_castom_node", NODE_INSTALLER)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            symlinks = list(getattr(mod, "SYMLINKS", []))
            if not symlinks:
                self.logger.print("  → SYMLINKS empty — no links to create")
                return
            created = 0
            for src, dst in symlinks:
                if not os.path.exists(src):
                    self.logger.print(
                        f"  → Source not found, skipping: {os.path.basename(src)}")
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.islink(dst) or os.path.exists(dst):
                    try:
                        os.remove(dst)
                    except OSError as e:
                        self.logger.print(
                            f"  → Could not remove {os.path.basename(dst)}: {e}")
                        continue
                try:
                    os.symlink(src, dst)
                    self.logger.print(f"  → Link: {os.path.basename(dst)}")
                    created += 1
                except OSError as e:
                    self.logger.print(
                        f"  → Symlink error {os.path.basename(dst)}: {e}")
            self.logger.print(f"  → Symlinks: {created}/{len(symlinks)}")
        except Exception as e:
            self.logger.print(f"[!] Could not create symlinks: {e}")

    # --- 2c. nvidia-ml-py instead of pynvml (suppress FutureWarning from torch 2.11) ---
    def _ensure_nvidia_ml_py(self):
        """Installs nvidia-ml-py and removes pynvml.

        Torch 2.11+ raises FutureWarning if outdated pynvml is installed
        instead of nvidia-ml-py. Runs every launch.
        """
        self.logger.print("  ── Checking nvidia-ml-py (pynvml → nvidia-ml-py) ──")
        try:
            r = subprocess.run(
                ["uv", "pip", "install", "--python", VENV_PYTHON,
                 "-q", "nvidia-ml-py"],
                capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                self.logger.print("  → nvidia-ml-py installed")
            else:
                self.logger.print(f"  → nvidia-ml-py: {r.stderr.strip()[:100]}")
        except Exception as e:
            self.logger.print(f"  → nvidia-ml-py: error ({e})")

        try:
            r = subprocess.run(
                ["uv", "pip", "uninstall", "--python", VENV_PYTHON,
                 "-q", "pynvml"],
                capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                self.logger.print("  → pynvml removed")
            else:
                self.logger.print("  → pynvml not found — OK")
        except Exception as e:
            self.logger.print(f"  → pynvml: error ({e})")

    # ------------------------------------------------------------------
    # 3. cloudflared
    # ------------------------------------------------------------------
    def _ensure_cloudflared(self):
        t0 = self._log_step("Step 4/6: Cloudflared (tunnel)")

        url = ("https://github.com/cloudflare/cloudflared/releases/latest/"
               "download/cloudflared-linux-amd64")
        if not os.path.exists(CLOUDFLARED):
            self.logger.print("  → Not found — downloading...")
            subprocess.run(["wget", "-q", url, "-O", CLOUDFLARED], check=True)
            size_mb = os.path.getsize(CLOUDFLARED) / 1024 / 1024
            self.logger.print(f"  → Downloaded: {size_mb:.1f} MB")
        else:
            size_mb = os.path.getsize(CLOUDFLARED) / 1024 / 1024
            self.logger.print(f"  → Already exists: {size_mb:.1f} MB")
            if size_mb < 5:
                self.logger.print("  → Size suspiciously small — re-downloading")
                try:
                    os.remove(CLOUDFLARED)
                except OSError:
                    pass
                subprocess.run(["wget", "-q", url, "-O", CLOUDFLARED], check=True)
                size_mb = os.path.getsize(CLOUDFLARED) / 1024 / 1024
                self.logger.print(f"  → Downloaded: {size_mb:.1f} MB")

        os.chmod(CLOUDFLARED, 0o755)
        self.logger.print("  → Permissions: 755 (+x)")
        self._log_elapsed(t0)

    # ------------------------------------------------------------------
    # 4b. SageAttention-SM75 (Turing T4) — custom attention node
    # ------------------------------------------------------------------
    def _install_sage_attention(self):
        """Installs SageAttention-SM75-path in venv + custom node.

        WARNING: DOES NOT WORK WITH GGUF MODELS (llama.cpp backend).
        Left for reference — call only for diffusion models (SD/SDXL/Flux).
        """
        try:
            self.sage_ok = sage_installer.install(
                home_dir=ke.HOME_DIR,
                venv_python=ke.VENV_PYTHON,
                comfy_dir=ke.COMFY_DIR,
                logger=self.logger,
            )
            if self.sage_ok:
                self.logger.print("  → SageAttention-SM75 active — "
                                  "attention via T4 custom node")
        except Exception as e:
            self.sage_ok = False
            self.logger.print(f"  → SageAttention: install error ({e}), "
                              "skipping — using SDPA")

    # ------------------------------------------------------------------
    # 5. Launch ComfyUI
    # ------------------------------------------------------------------
    def _start_comfy(self):
        self._log_step("Step 6/7: Launching ComfyUI", status="⏳ Launching ComfyUI...")
        if self.sage_ok:
            self.logger.print("  → Attention: SageAttention-SM75 (T4 custom node)")
        else:
            self.logger.print("  → Attention: torch SDPA (default)")

        # Disable comfy-aimdo — on Kaggle its async file reading
        # causes hostbuf_file_reader_read failed → CUDA illegal memory access.
        os.environ["COMFY_AIMDO_ENABLED"] = "0"

        comfy_args = [
            VENV_PYTHON, "main.py",
            "--listen", "0.0.0.0",
            "--port", str(PORT),
            "--enable-cors-header", "*",
            "--disable-auto-launch",
            "--preview-method", "auto",
            # Without attention flag — ComfyUI uses torch SDPA (on torch 2+).
            # Previously used --use-split-cross-attention, but on the second pass
            # 720p video caused OOM. SDPA is more memory-efficient on T4.
            # If OOM-killer (SIGKILL -9) occurs during model loading —
            # restore --use-split-cross-attention.
            #
            # --gpu-only: added for testing but causes CUDA OOM
            # (VRAM eviction). Removed.
        ]

        cmd_str = " ".join(comfy_args)
        self.logger.print(f"  → Command: {cmd_str}")

        self.comfy_proc = subprocess.Popen(
            comfy_args,
            cwd=COMFY_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.logger.print(f"  → PID: {self.comfy_proc.pid}")
        Thread(target=self.logger.stream_process,
               args=(self.comfy_proc, "[COMFY] "),
               daemon=True).start()

    # ------------------------------------------------------------------
    # 5. Wait for port
    # ------------------------------------------------------------------
    def _wait_for_port(self):
        self.logger.print(f"\n{'─'*40}")
        self.logger.print("  Waiting for ComfyUI to start...")
        start = time.time()
        last_report = 0
        while True:
            # First check port — if open, ComfyUI is working,
            # even if poll() erroneously returned a code (race condition restart).
            try:
                with socket.create_connection(("127.0.0.1", PORT), timeout=2):
                    break
            except OSError:
                pass
            # Only then check the process — but only if port is closed
            if self.comfy_proc.poll() is not None:
                raise RuntimeError(
                    f"ComfyUI exited with code {self.comfy_proc.returncode}")
            elapsed = time.time() - start
            if elapsed > STARTUP_TIMEOUT:
                raise RuntimeError(f"Timeout ({STARTUP_TIMEOUT}s)")
            if elapsed - last_report >= 10:
                self.logger.print(f"  ⏳ {elapsed:.0f}s elapsed (timeout {STARTUP_TIMEOUT}s)")
                last_report = elapsed
            time.sleep(2)
        elapsed = time.time() - start
        self.logger.print(f"  ✅ ComfyUI started in {elapsed:.1f}s")
        self.logger.set_status("✅ ComfyUI running, starting tunnel...", "#27ae60")

    # ------------------------------------------------------------------
    # 6. Cloudflare tunnel + URL parsing
    # ------------------------------------------------------------------
    def _start_tunnel(self):
        t0 = self._log_step("Step 6/6: Cloudflare tunnel")

        url = f"http://127.0.0.1:{PORT}"
        self.logger.print(f"  → Target: {url}")

        self.tunnel_proc = subprocess.Popen(
            [CLOUDFLARED, "tunnel", "--no-autoupdate", "--protocol", "http2",
             "--url", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.logger.print(f"  → cloudflared PID: {self.tunnel_proc.pid}")

        # Parse public URL from cloudflared output
        # (single reader — no stream_process thread to avoid pipe race)
        start = time.time()
        while time.time() - start < URL_TIMEOUT:
            line = self.tunnel_proc.stdout.readline()
            if not line:
                if self.tunnel_proc.poll() is not None:
                    raise RuntimeError("cloudflared exited unexpectedly")
                continue
            self.logger.print(f"[TUNNEL] {line.rstrip()}")
            m = re.search(r"https://[^\s]+trycloudflare\.com", line)
            if m:
                self.public_url = m.group(0)
                break
        else:
            raise RuntimeError(f"Timeout ({URL_TIMEOUT}s) waiting for Cloudflare URL")

        self.logger.print(f"  → Public URL: {self.public_url}")
        self.logger.set_status("✅ ComfyUI ready!", "#27ae60")
        self.logger.show_url(self.public_url)
        self._log_elapsed(t0)

    # ------------------------------------------------------------------
    # Kill all managed processes
    # ------------------------------------------------------------------
    def _kill_processes(self):
        for name, proc in [("ComfyUI", self.comfy_proc), ("tunnel", self.tunnel_proc)]:
            if proc and proc.poll() is None:
                self.logger.print(f"  → Stopping {name} (PID {proc.pid})...")
                try:
                    proc.terminate()
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                except OSError:
                    pass
        self.comfy_proc = None
        self.tunnel_proc = None

        # Kill any leftover processes by pattern
        for pat in ("main.py", "comfyui", "cloudflared"):
            try:
                subprocess.run(["pkill", "-9", "-f", pat], capture_output=True)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Stop button
    # ------------------------------------------------------------------
    def _on_stop(self):
        if self.stopped:
            return
        self.stopped = True
        self._starting = False       # reset — so Restart doesn't get ignored
        self.logger.set_status("⏳ Stopping ComfyUI...", "#f39c12")
        self.logger.disable_stop_btn()
        self._kill_processes()
        self.logger.hide_url()
        self.logger.set_status("🛑 ComfyUI stopped. Press «Restart».",
                               "#e74c3c")
        self.logger.print("[*] ComfyUI and tunnel stopped.")

    # ------------------------------------------------------------------
    # Restart button
    # ------------------------------------------------------------------
    def _on_restart(self):
        if self._starting:
            return
        self._starting = True           # block double-click
        self.logger.disable_restart_btn()
        self.logger.set_status("🔄 Restarting ComfyUI...", "#f39c12")
        self.logger.print("[*] Restart: killing old processes...")
        self._kill_processes()
        # Reset state for new launch
        self.stopped = False
        self.public_url = None
        self.comfy_proc = None
        self.tunnel_proc = None
        self.logger.hide_url()
        self.logger.enable_stop_btn()
        Thread(target=self._startup, daemon=True).start()

    # ------------------------------------------------------------------
    # keep-alive: cell active + pump for buttons
    # ------------------------------------------------------------------
    def _make_kernel_pump(self):
        """Creates a pump for processing kernel events (on_click buttons).

        Uses nest_asyncio to execute the coroutine
        kernel.do_one_iteration() from the synchronous keep-alive loop.

        Returns the pump() function or None if it couldn't be created.
        """
        try:
            import asyncio
            try:
                import nest_asyncio
            except ImportError:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-q",
                     "nest_asyncio"], check=False)
                import nest_asyncio

            from IPython import get_ipython
            ip = get_ipython()
            if ip is None or not hasattr(ip, "kernel"):
                return None
            kernel = ip.kernel
            nest_asyncio.apply()
            loop = asyncio.get_event_loop()

            def pump():
                res = kernel.do_one_iteration()
                if asyncio.iscoroutine(res):
                    loop.run_until_complete(res)

            return pump
        except Exception:
            return None

    def _keep_alive(self):
        """Keeps the cell active — Kaggle won't put the session to sleep.

        In loop: pump (button on_click handling) + sleep 0.05s.
        Stops via "Stop" button, "Restart" button, or ⏹ Interrupt.
        """
        pump = self._make_kernel_pump()
        if pump is None:
            self.logger.print(
                "[!] Pump not created — buttons won't work, "
                "use ⏹ Interrupt to stop.")
        self.logger.print("[*] keep-alive active — Kaggle won't sleep. "
                          "Stop via panel button or ⏹ (Interrupt).")
        try:
            while not self.stopped:
                if pump is not None:
                    try:
                        pump()
                    except Exception:
                        time.sleep(0.2)
                time.sleep(0.05)
        except KeyboardInterrupt:
            self.logger.print("[*] Interrupt — stopping ComfyUI "
                              "and tunnel...")
            # Call on_stop as if the button was pressed
            self._on_stop()
        self.logger.flush_now()
