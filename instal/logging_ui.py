#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
logging_ui.py
=================================================================
UI wrapper and logging system for ComfyUI on Kaggle.

Architecture (painstakingly developed on Kaggle):
  * Log — widgets.HTML with <pre> and overflow-y:auto.
    No JS. No append_stdout. No auto-scroll.
    Browser scroll anchoring:
      - user at bottom → new lines visible (content stays at bottom)
      - user reading above → scroll is NOT janked
  * Buffer + flusher (every 0.5s) — batch lines to avoid sending
    the full log on every keystroke.
  * Status, heartbeat, URL — widgets.HTML.
  * Buttons — widgets.Button with on_click.
  * Keep-alive: background threads (_heartbeat_loop, _stdout_keep_alive).
=================================================================
"""

import html
import os
import re
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from threading import Lock, Thread

import ipywidgets as widgets
from IPython.display import display


# ----------------------------------------------------------------------
# Log settings
# ----------------------------------------------------------------------
LOG_MAX_LINES = 2000     # how many recent lines to keep in buffer
LOG_FLUSH_SEC = 0.5      # how often to flush batch to HTML widget

LOG_FILE_PATH = "/kaggle/working/comfyui_launcher.log"


_LONG_LOG_STUB = "<pre style='margin:0;padding:8px;font-style:italic;color:#888;'>Log will appear after launch...</pre>"


# ----------------------------------------------------------------------
# Internal HTML log template
# ----------------------------------------------------------------------
def _log_html_body(text):
    """Just <pre> with text — scroll is managed by the widget layout.

    Why NOT a wrapper div inside HTML:
      Each time .value = new_html a new DOM is created.
      If there's a scrollable div inside — its scrollTop resets to top.

      The widget layout (overflow:auto on the root element) is NOT
      recreated — only innerHTML changes. The browser preserves
      scrollTop of a stable element. Scroll doesn't jump.
    """
    return (
        "<pre style='margin:0;padding:8px;"
        "background:#1e1e1e;color:#d4d4d4;"
        "font-family:monospace;font-size:13px;"
        "white-space:pre-wrap;word-wrap:break-word;'>"
        f"{text}</pre>"
    )


class LogManager:
    """Collects logs from all threads and draws the control panel.

    Log — widgets.HTML + <pre>. Lines accumulate in a buffer (deque)
    and are flushed as a batch every 0.5s.

    Scroll anchoring:
      The browser manages the scroll of the scrollable container itself.
      If the user is at the bottom — new lines push old ones up,
      scroll stays at the bottom (reader sees latest lines).
      If the user scrolled up — scroll is NOT janked,
      content under the viewport doesn't shift.
    """

    _ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def __init__(self):
        # Log buffer
        self._log_lines = deque(maxlen=LOG_MAX_LINES)
        self._log_lock = Lock()
        self._log_dirty = False

        self.stopped = False

        # Button callbacks (set from launcher.py)
        self.on_stop_callback = None
        self.on_restart_callback = None

        # Persistent log file
        self._log_file = self._open_log_file()

        # Build panel
        self._build_ui()

        # Flusher — flushes buffer to HTML widget every 0.5s
        Thread(target=self._log_flusher, daemon=True).start()

    # ------------------------------------------------------------------
    # Persistent log to file
    # ------------------------------------------------------------------
    @staticmethod
    def _open_log_file():
        try:
            f = open(LOG_FILE_PATH, "a", encoding="utf-8")
            f.write(f"\n--- Launch {datetime.now()} ---\n")
            f.flush()
            return f
        except OSError:
            return None

    def _close_log_file(self):
        if self._log_file:
            try:
                self._log_file.write(f"--- Stop {datetime.now()} ---\n\n")
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None

    # ------------------------------------------------------------------
    # UI assembly
    # ------------------------------------------------------------------
    def _build_ui(self):
        # Status
        self.status = widgets.HTML(self._status_html("⏳ Starting...", "#f39c12"))

        # Heartbeat
        self._hb_started = time.time()
        self.heartbeat = widgets.HTML(self._heartbeat_html(0))

        # URL link
        self.url_box = widgets.HTML(
            "<div style='font-style:italic; color:#555'>"
            "Public link will appear here...</div>"
        )

        # "Stop" button
        self.stop_btn = widgets.Button(
            description="🛑 Stop",
            button_style="danger",
            layout=widgets.Layout(width="160px", height="42px"),
        )
        self.stop_btn.on_click(self._on_stop_click)

        # "Restart" button
        self.restart_btn = widgets.Button(
            description="🔄 Restart",
            button_style="warning",
            layout=widgets.Layout(width="180px", height="42px"),
        )
        self.restart_btn.on_click(self._on_restart_click)

        # Button row
        self.controls = widgets.HBox([self.url_box, self.stop_btn, self.restart_btn])

        # Log — widgets.HTML with <pre>.
        # Scroll — on widget layout (overflow:auto, root element is
        # stable, scrollTop preserved on innerHTML change).
        self.log_output = widgets.HTML(
            value=_LONG_LOG_STUB,
            layout=widgets.Layout(
                border="1px solid #444", height="360px",
                overflow="auto",
            ),
        )

        # Assemble panel
        self.panel = widgets.VBox([
            self.status,
            self.heartbeat,
            self.controls,
            widgets.HTML("<b>Log:</b>"),
            self.log_output,
        ])

        # Show panel
        display(self.panel)

    # ------------------------------------------------------------------
    # HTML generators (for status, heartbeat)
    # ------------------------------------------------------------------
    @staticmethod
    def _status_html(text, color):
        return f"<h3 style='color:{color}; margin:6px 0; font-size:16px'>{text}</h3>"

    @staticmethod
    def _heartbeat_html(elapsed_sec):
        ticks = int(elapsed_sec // 30)
        h, rem = divmod(int(elapsed_sec), 3600)
        m, s = divmod(rem, 60)
        up = f"{h:d}h {m:02d}m {s:02d}s" if h else f"{m:d}m {s:02d}s"
        return (
            "<div style='font-family:monospace; font-size:13px; color:#2ecc71; "
            "background:#0f1117; border-left:3px solid #2ecc71; "
            "padding:6px 12px; margin:4px 0; border-radius:4px;'>"
            f"💚 keep-alive · tick #{ticks} · uptime {up} · "
            "Kaggle won't sleep</div>"
        )

    # ------------------------------------------------------------------
    # Public update methods
    # ------------------------------------------------------------------
    def set_status(self, text, color):
        self.status.value = self._status_html(text, color)

    def show_url(self, url):
        self.url_box.value = (
            f"<a href='{url}' target='_blank' rel='noopener noreferrer' "
            f"style='background:#3498db; color:#fff; padding:10px 22px; "
            f"text-decoration:none; border-radius:8px; font-size:15px; "
            f"font-weight:bold; display:inline-block; margin-right:12px;'>"
            f"🔗 Open ComfyUI</a>"
            f"<div style='font-size:11px; color:#888; margin-top:4px'>{url}</div>"
        )

    def hide_url(self):
        self.url_box.value = (
            "<div style='font-style:italic; color:#555'>"
            "ComfyUI stopped.</div>"
        )

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------
    def _on_stop_click(self, _btn):
        if self.on_stop_callback:
            self.on_stop_callback()

    def _on_restart_click(self, _btn):
        if self.on_restart_callback:
            self.on_restart_callback()

    # ------------------------------------------------------------------
    # Button states
    # ------------------------------------------------------------------
    def disable_stop_btn(self):
        self.stop_btn.disabled = True

    def enable_stop_btn(self):
        self.stop_btn.disabled = False

    def disable_restart_btn(self):
        self.restart_btn.disabled = True

    def enable_restart_btn(self):
        self.restart_btn.disabled = False

    # ------------------------------------------------------------------
    # Heartbeat (widgets.HTML — no pump required)
    # ------------------------------------------------------------------
    def _heartbeat_loop(self):
        while not self.stopped:
            try:
                self.heartbeat.value = self._heartbeat_html(
                    time.time() - self._hb_started)
            except Exception:
                pass
            for _ in range(30):
                if self.stopped:
                    return
                time.sleep(1)

    # ------------------------------------------------------------------
    # stdout keep-alive (anti-sleep via print)
    # ------------------------------------------------------------------
    def _stdout_keep_alive(self):
        print("\n🔒 [PROTECTION] Kaggle protection system activated!", flush=True)
        print("🔒 [PROTECTION] Will send pulse every 5 minutes\n", flush=True)
        while not self.stopped:
            for _ in range(300):
                if self.stopped:
                    return
                time.sleep(1)
            now = datetime.now().strftime("%H:%M:%S")
            print(f"💓 [{now}] ComfyUI active, waiting for request...", flush=True)

    # ------------------------------------------------------------------
    # Log: buffer + batch flush to HTML widget
    # ------------------------------------------------------------------
    @staticmethod
    def _strip_ansi(text):
        return LogManager._ANSI_RE.sub('', text)

    def print(self, text):
        """Puts lines in buffer. Flusher sends batch to HTML every 0.5s.

        Batching + HTML widget:
          - doesn't trigger frontend auto-scroll (like Output.append_stdout)
          - browser scroll anchoring preserves user position
          - html.escape() protects against malformed HTML in logs
        """
        for raw in str(text).split("\n"):
            seg = raw.split("\r")[-1].rstrip()
            if not seg:
                continue
            seg = self._strip_ansi(seg)
            if not seg:
                continue
            with self._log_lock:
                self._log_lines.append(seg)
                self._log_dirty = True
                if self._log_file:
                    try:
                        self._log_file.write(f"{seg}\n")
                    except OSError:
                        pass

    def _flush_log_now(self):
        """Flushes buffer to HTML widget.

        Safe order:
          1. Copy lines under lock
          2. Release lock
          3. Send to widget
        No .clear() — deque auto-drops old entries by maxlen.
        """
        with self._log_lock:
            if not self._log_dirty:
                return
            self._log_dirty = False
            lines = list(self._log_lines)
        if lines:
            safe = "\n".join(html.escape(l) for l in lines)
            try:
                self.log_output.value = _log_html_body(safe)
                if self._log_file:
                    self._log_file.flush()
            except Exception:
                pass

    def _log_flusher(self):
        """Flushes buffer to HTML widget every 0.5s."""
        while not self.stopped:
            time.sleep(LOG_FLUSH_SEC)
            try:
                self._flush_log_now()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Process stdout capture → log
    # ------------------------------------------------------------------
    def stream_process(self, proc, prefix):
        for line in iter(proc.stdout.readline, ""):
            if line:
                self.print(f"{prefix}{line.rstrip()}")
            if proc.poll() is not None and not line:
                break

    def _run_subprocess(self, cmd, **kwargs):
        try:
            preexec_fn = os.setpgrp
        except AttributeError:
            preexec_fn = None
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
            preexec_fn=preexec_fn,
            **kwargs,
        )
        return proc

    def stream_script(self, path, label, hint):
        if not os.path.exists(path):
            raise RuntimeError(f"Installer not found: {path}. {hint}")
        self.print(f"[*] Running: {path}")
        try:
            python_bin = sys.executable
        except NameError:
            raise RuntimeError(
                "sys not imported — probably stale __pycache__.\n"
                "Delete instal/__pycache__/ and re-run the cell.")
        proc = self._run_subprocess([python_bin, path])
        try:
            for line in iter(proc.stdout.readline, ""):
                if line:
                    self.print(f"[{label}] {line.rstrip()}")
                if proc.poll() is not None and not line:
                    break
        except OSError:
            pass
        except KeyboardInterrupt:
            self.print(f"[!] Interrupt received — finishing {path}")
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
            raise
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(
                f"{path} exited with code {proc.returncode}. {hint}")

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    def flush_now(self):
        try:
            self._flush_log_now()
        except Exception:
            pass
        if self._log_file:
            try:
                self._log_file.flush()
            except OSError:
                pass

    def stop(self):
        self.stopped = True
        self.flush_now()
        self._close_log_file()
