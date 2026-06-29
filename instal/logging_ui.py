#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
logging_ui.py
=================================================================
UI-обвязка и система логирования для ComfyUI на Kaggle.

Архитектура (выстрадана на Kaggle):
  * Лог — widgets.HTML с <pre> и overflow-y:auto.
    Без JS. Без append_stdout. Без авто-скролла.
    Браузерное scroll anchoring:
      - пользователь внизу → новые строки видны (content stays at bottom)
      - пользователь читает выше → скролл НЕ дёргается
  * Буфер + флешер (раз в 0.5с) — батчим строки, чтобы не слать
    полный лог на каждый чих.
  * Статус, heartbeat, URL — widgets.HTML.
  * Кнопки — widgets.Button с on_click.
  * Keep-alive: фоновые потоки (_heartbeat_loop, _stdout_keep_alive).
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
LOG_FLUSH_SEC = 0.5      # как часто сбрасываем батч в HTML-виджет

LOG_FILE_PATH = "/kaggle/working/comfyui_launcher.log"


_LONG_LOG_STUB = "<pre style='margin:0;padding:8px;font-style:italic;color:#888;'>Лог появится после запуска...</pre>"


# ----------------------------------------------------------------------
# Внутренний HTML-шаблон лога
# ----------------------------------------------------------------------
def _log_html_body(text):
    """Просто <pre> с текстом — скроллом управляет layout виджета.

    Почему НЕ wrapper div внутри HTML:
      Каждый раз при .value = new_html создаётся новый DOM.
      Если scrollable div внутри — его scrollTop сбрасывается наверх.

      Layout виджета (overflow:auto на корневом элементе) НЕ
      пересоздаётся — только innerHTML меняется. Браузер сохраняет
      scrollTop стабильного элемента. Скролл не прыгает.
    """
    return (
        "<pre style='margin:0;padding:8px;"
        "background:#1e1e1e;color:#d4d4d4;"
        "font-family:monospace;font-size:13px;"
        "white-space:pre-wrap;word-wrap:break-word;'>"
        f"{text}</pre>"
    )


class LogManager:
    """Собирает логи из всех потоков и рисует панель управления.

    Лог — widgets.HTML + <pre>. Строки накапливаются в буфере (deque)
    и сбрасываются батчем раз в 0.5с.

    Scroll anchoring:
      Браузер сам управляет скроллом прокручиваемого контейнера.
      Если пользователь внизу — новые строки смещают старые вверх,
      скролл остаётся внизу (читатель видит последние строки).
      Если пользователь прокрутил вверх — скролл НЕ дёргается,
      контент под viewport'ом не сдвигается.
    """

    _ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def __init__(self):
        # Буфер лога
        self._log_lines = deque(maxlen=LOG_MAX_LINES)
        self._log_lock = Lock()
        self._log_dirty = False

        self.stopped = False

        # Callback'и для кнопок (устанавливаются из launcher.py)
        self.on_stop_callback = None
        self.on_restart_callback = None

        # Persistent-файл лога
        self._log_file = self._open_log_file()

        # Строим панель
        self._build_ui()

        # Флешер — раз в 0.5с сбрасывает буфер в HTML-виджет
        Thread(target=self._log_flusher, daemon=True).start()

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
    # Сборка UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        # Статус
        self.status = widgets.HTML(self._status_html("⏳ Запуск...", "#f39c12"))

        # Heartbeat
        self._hb_started = time.time()
        self.heartbeat = widgets.HTML(self._heartbeat_html(0))

        # URL-ссылка
        self.url_box = widgets.HTML(
            "<div style='font-style:italic; color:#555'>"
            "Публичная ссылка появится здесь...</div>"
        )

        # Кнопка «Остановить»
        self.stop_btn = widgets.Button(
            description="🛑 Остановить",
            button_style="danger",
            layout=widgets.Layout(width="160px", height="42px"),
        )
        self.stop_btn.on_click(self._on_stop_click)

        # Кнопка «Перезапустить»
        self.restart_btn = widgets.Button(
            description="🔄 Перезапустить",
            button_style="warning",
            layout=widgets.Layout(width="180px", height="42px"),
        )
        self.restart_btn.on_click(self._on_restart_click)

        # Ряд кнопок
        self.controls = widgets.HBox([self.url_box, self.stop_btn, self.restart_btn])

        # Лог — widgets.HTML с <pre>.
        # Скролл — на layout виджета (overflow:auto, корневой элемент
        # стабильный, scrollTop сохраняется при смене innerHTML).
        self.log_output = widgets.HTML(
            value=_LONG_LOG_STUB,
            layout=widgets.Layout(
                border="1px solid #444", height="360px",
                overflow="auto",
            ),
        )

        # Собираем панель
        self.panel = widgets.VBox([
            self.status,
            self.heartbeat,
            self.controls,
            widgets.HTML("<b>Лог:</b>"),
            self.log_output,
        ])

        # Показываем панель
        display(self.panel)

    # ------------------------------------------------------------------
    # HTML-генераторы (для статуса, heartbeat)
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

    # ------------------------------------------------------------------
    # Публичные методы обновления
    # ------------------------------------------------------------------
    def set_status(self, text, color):
        self.status.value = self._status_html(text, color)

    def show_url(self, url):
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
    # Обработчики кнопок
    # ------------------------------------------------------------------
    def _on_stop_click(self, _btn):
        if self.on_stop_callback:
            self.on_stop_callback()

    def _on_restart_click(self, _btn):
        if self.on_restart_callback:
            self.on_restart_callback()

    # ------------------------------------------------------------------
    # Состояние кнопок
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
    # Heartbeat (widgets.HTML — не требует pump)
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
    # Лог: буфер + батчевый сброс в HTML-виджет
    # ------------------------------------------------------------------
    @staticmethod
    def _strip_ansi(text):
        return LogManager._ANSI_RE.sub('', text)

    def print(self, text):
        """Кладёт строки в буфер. Флешер сбрасывает батч в HTML раз в 0.5с.

        Батчинг + HTML-виджет:
          - не триггерит авто-скролл frontend'а (как Output.append_stdout)
          - браузерное scroll anchoring сохраняет позицию пользователя
          - html.escape() защищает от некорректного HTML в логах
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
        """Сбрасывает буфер в HTML-виджет.

        Безопасный порядок:
          1. Копируем lines под lock'ом
          2. Снимаем lock
          3. Шлём в виджет
        Никаких .clear() — deque сам дропает старые записи по maxlen.
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
        """Раз в 0.5с сбрасывает буфер в HTML-виджет."""
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
        if self._log_file:
            try:
                self._log_file.flush()
            except OSError:
                pass

    def stop(self):
        self.stopped = True
        self.flush_now()
        self._close_log_file()
