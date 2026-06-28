#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
logging_ui.py
=================================================================
UI-обвязка и система логирования для ComfyUI на Kaggle.

Архитектура (выстрадана на Kaggle):
  * Лог — widgets.HTML (НЕ Output!). .value = html работает из любого
    потока через iopub, не требует event-loop pump.
  * Статус, heartbeat, URL — тоже widgets.HTML (те же преимущества).
  * Кнопки‑виджеты (Button) НЕ РАБОТАЮТ без nest_asyncio + pump,
    который ломает ячейку. Поэтому используем ⏹ Interrupt в тулбаре
    Kaggle + HTML-инструкцию.
  * Keep-alive: простой time.sleep(0.1) + flush, никаких pump.
  * Два anti-sleep маяка: heartbeat (через widgets.HTML) + stdout print.

Фикс бага лога (история):
  * Изначально был widgets.HTML — работало.
  * Потом переделали на widgets.Output с clear_output() — сломалось,
    т.к. Output требует pump.
  * Сейчас снова widgets.HTML — работает без pump.
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
# Настройки лога
# ----------------------------------------------------------------------
LOG_MAX_LINES = 2000     # сколько последних строк держим в буфере
LOG_FLUSH_SEC = 0.5      # как часто перерисовываем виджет лога

LOG_FILE_PATH = "/kaggle/working/comfyui_launcher.log"


class LogManager:
    """Собирает логи из всех потоков и рисует панель управления.

    Потокобезопасен: print() можно звать откуда угодно.
    Лог — widgets.HTML, .value = html работает из любого потока.
    """

    _ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def __init__(self):
        # Буфер лога + троттлинг
        self._log_lines = deque(maxlen=LOG_MAX_LINES)
        self._log_lock = Lock()
        self._log_dirty = False

        self.stopped = False

        # Persistent-файл лога
        self._log_file = self._open_log_file()

        # Строим панель
        self._build_ui()

    # ------------------------------------------------------------------
    # Persistent-лог в файл
    # ------------------------------------------------------------------
    @staticmethod
    def _open_log_file():
        try:
            f = open(LOG_FILE_PATH, "a", encoding="utf-8")
            f.write(f"\n--- Запуск {datetime.now()} ---\n")
            f.flush()
            return f
        except OSError:
            return None

    def _close_log_file(self):
        if self._log_file:
            try:
                self._log_file.write(f"--- Остановка {datetime.now()} ---\n\n")
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None

    # ------------------------------------------------------------------
    # Сборка UI — ТОЛЬКО widgets.HTML (не Button, не Output!)
    # ------------------------------------------------------------------
    def _build_ui(self):
        # Статус
        self.status = widgets.HTML(self._status_html("⏳ Запуск...", "#f39c12"))

        # Heartbeat
        self._hb_started = time.time()
        self.heartbeat = widgets.HTML(self._heartbeat_html(0))

        # URL-ссылка (появится, когда туннель даст URL)
        self.url_box = widgets.HTML(
            "<div style='font-style:italic; color:#555'>"
            "Публичная ссылка появится здесь...</div>"
        )

        # Кнопки — НЕ widgets.Button (не работают без pump).
        # Вместо них — HTML-блок с инструкцией по Interrupt.
        self.controls = widgets.HTML(
            "<div style='margin:8px 0; padding:8px 12px; "
            "background:#1a1a2e; border-radius:6px; font-size:13px;'>"
            "<span style='color:#e74c3c; font-weight:bold'>⏹ Остановка:</span> "
            "<span style='color:#ccc'>нажми ⏹ (Interrupt) в тулбаре Kaggle</span>"
            "</div>"
        )

        # Лог — widgets.HTML (НЕ Output!). .value = html обновляется
        # из флешера — работает через iopub, не требует pump.
        self.log = widgets.HTML(
            value=self._log_html([]),
            layout=widgets.Layout(
                border="1px solid #444", height="360px",
                overflow="auto", padding="0",
            ),
        )

        # Собираем панель
        self.panel = widgets.VBox([
            self.status,
            self.heartbeat,
            self.url_box,
            self.controls,
            widgets.HTML("<b>Лог:</b>"),
            self.log,
        ])

    # ------------------------------------------------------------------
    # HTML-генераторы
    # ------------------------------------------------------------------
    @staticmethod
    def _status_html(text, color):
        return f"<h3 style='color:{color}; margin:6px 0; font-size:16px'>{text}</h3>"

    @staticmethod
    def _heartbeat_html(elapsed_sec):
        ticks = int(elapsed_sec // 30)
        h, rem = divmod(int(elapsed_sec), 3600)
        m, s = divmod(rem, 60)
        up = f"{h:d}ч {m:02d}м {s:02d}с" if h else f"{m:d}м {s:02d}с"
        return (
            "<div style='font-family:monospace; font-size:13px; color:#2ecc71; "
            "background:#0f1117; border-left:3px solid #2ecc71; "
            "padding:6px 12px; margin:4px 0; border-radius:4px;'>"
            f"💚 keep-alive · тик #{ticks} · аптайм {up} · "
            "Kaggle не уснёт</div>"
        )

    @staticmethod
    def _log_html(lines):
        """Собирает HTML для виджета лога."""
        body = html.escape("\n".join(lines))
        return (
            "<pre style='margin:0; padding:6px; white-space:pre-wrap; "
            "word-break:break-word; background:#0f1117; color:#ddd; "
            "font-family:monospace; font-size:12px; line-height:1.35; "
            "min-height:100%;'>" + body + "</pre>"
        )

    # ------------------------------------------------------------------
    # Публичные методы обновления
    # ------------------------------------------------------------------
    def set_status(self, text, color):
        """Обновляет строку статуса."""
        self.status.value = self._status_html(text, color)

    def show_url(self, url):
        """Показывает URL туннеля."""
        self.url_box.value = (
            f"<a href='{url}' target='_blank' rel='noopener noreferrer' "
            f"style='background:#3498db; color:#fff; padding:10px 22px; "
            f"text-decoration:none; border-radius:8px; font-size:15px; "
            f"font-weight:bold; display:inline-block; margin-right:12px;'>"
            f"🔗 Открыть ComfyUI</a>"
            f"<div style='font-size:11px; color:#888; margin-top:4px'>{url}</div>"
        )

    def hide_url(self):
        self.url_box.value = (
            "<div style='font-style:italic; color:#555'>"
            "ComfyUI остановлен.</div>"
        )

    # ------------------------------------------------------------------
    # Heartbeat (anti-sleep через widgets.HTML)
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
    # stdout keep-alive (anti-sleep через print)
    # ------------------------------------------------------------------
    def _stdout_keep_alive(self):
        print("\n🔒 [ЗАЩИТА] Система защиты Kaggle активирована!", flush=True)
        print("🔒 [ЗАЩИТА] Буду отправлять пульс каждые 5 минут\n", flush=True)
        while not self.stopped:
            for _ in range(300):
                if self.stopped:
                    return
                time.sleep(1)
            now = datetime.now().strftime("%H:%M:%S")
            print(f"💓 [{now}] ComfyUI активен, ожидание запроса...", flush=True)

    # ------------------------------------------------------------------
    # Лог: дешёвая запись в буфер + троттлинг-перерисовка
    # ------------------------------------------------------------------
    @staticmethod
    def _strip_ansi(text):
        return LogManager._ANSI_RE.sub('', text)

    def print(self, text):
        """Кладёт строки в буфер. Флешер перерисовывает виджет.

        Дублирует строки в sys.stdout (видно в ячейке) и в persistent-файл.
        """
        for raw in str(text).split("\n"):
            seg = raw.split("\r")[-1].rstrip()
            if not seg:
                continue
            seg = self._strip_ansi(seg)
            if not seg:
                continue
            # Пишем в stdout — всегда видно в ячейке
            sys.stdout.write(f"{seg}\n")
            with self._log_lock:
                self._log_lines.append(seg)
                self._log_dirty = True
                if self._log_file:
                    try:
                        self._log_file.write(f"{seg}\n")
                    except OSError:
                        pass

    def _flush_log_now(self):
        """Сбрасывает буфер в widgets.HTML — просто .value = html."""
        with self._log_lock:
            if not self._log_dirty:
                return
            self._log_dirty = False
            lines = list(self._log_lines)
        try:
            self.log.value = self._log_html(lines)
            if self._log_file:
                self._log_file.flush()
        except Exception:
            pass

    def _log_flusher(self):
        """Раз в LOG_FLUSH_SEC перерисовывает виджет лога."""
        while not self.stopped:
            time.sleep(LOG_FLUSH_SEC)
            try:
                self._flush_log_now()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Захват stdout процесса -> лог
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
            raise RuntimeError(f"Установщик не найден: {path}. {hint}")
        self.print(f"[*] Запускаю: {path}")
        try:
            python_bin = sys.executable
        except NameError:
            raise RuntimeError(
                "sys не импортирован — вероятно, stale __pycache__.\n"
                "Удали instal/__pycache__/ и перезапусти ячейку.")
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
            self.print(f"[!] Получен Interrupt — завершаю {path}")
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
            raise
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(
                f"{path} завершился с кодом {proc.returncode}. {hint}")

    # ------------------------------------------------------------------
    # Завершение
    # ------------------------------------------------------------------
    def flush_now(self):
        try:
            self._flush_log_now()
        except Exception:
            pass

    def stop(self):
        self.stopped = True
        self.flush_now()
        self._close_log_file()
