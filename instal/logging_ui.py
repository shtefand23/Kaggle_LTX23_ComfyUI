#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
logging_ui.py
=================================================================
UI-обвязка и система логирования для ComfyUI на Kaggle.

Что тут:
  * LogManager — строит панель виджетов (статус, кнопки, лог, heartbeat).
  * Троттлинг лога: строки пишутся в ограниченный deque (LOG_MAX_LINES),
    перерисовка раз в LOG_FLUSH_SEC через отдельный поток-флешер.
    Без этого блокнот/браузер виснут от потока строк ComfyUI/tqdm.
  * Два anti-sleep маяка:
      - heartbeat (виджет, трафик ядро->браузер)
      - stdout keep-alive (print, защита от 'Are you still there?')

Фикс бага лога:
  clear_output(wait=True) вешал флешер в фоновом потоке — ждал подтверждения
  от ядра, которое не приходило. Заменено на wait=False.
=================================================================
"""

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
# Настройки лога — меняй здесь, не в start.py
# ----------------------------------------------------------------------
LOG_MAX_LINES = 2000     # сколько последних строк держим в буфере
LOG_FLUSH_SEC = 0.5      # как часто перерисовываем виджет лога

# Путь к persistent-файлу лога (сохраняет ВСЕ строки, не только последние).
# Лежит в /kaggle/working — переживает рестарт сессии.
LOG_FILE_PATH = "/kaggle/working/comfyui_launcher.log"


class LogManager:
    """Собирает логи из всех потоков/процессов и рисует панель управления.

    Потокобезопасен: _print() можно звать откуда угодно, флешер в своей
    нити раз в LOG_FLUSH_SEC дёргает _flush_log_now().
    """

    _ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def __init__(self):
        # Буфер лога (ограниченный) + троттлинг
        self._log_lines = deque(maxlen=LOG_MAX_LINES)
        self._log_lock = Lock()
        self._log_dirty = False
        self._log_rendered = 0   # сколько строк уже выведено в Output

        # Флаг остановки — из него же читают heartbeat/keep-alive потоки
        self.stopped = False

        # Persistent-файл лога — сохраняет ВСЕ строки на диск
        self._log_file = self._open_log_file()

        # Ссылка на внешний обработчик для кнопки «Остановить» / «Перезапустить».
        # Устанавливается из launcher.py после создания LogManager.
        self.on_stop_callback = None
        self.on_restart_callback = None

        # --- Собираем UI ---
        self._build_ui()

    # ------------------------------------------------------------------
    # Persistent-лог в файл (все строки, не только последние 2000)
    # ------------------------------------------------------------------
    @staticmethod
    def _open_log_file():
        """Открывает файл лога в /kaggle/working для дописывания.

        Если файл открыть не удалось (не Kaggle, нет прав) — тихо
        возвращаем None, лог пишется только в виджет.
        """
        try:
            f = open(LOG_FILE_PATH, "a", encoding="utf-8")
            f.write(f"\n--- Запуск {datetime.now()} ---\n")
            f.flush()
            return f
        except OSError:
            return None

    def _close_log_file(self):
        """Закрывает файл лога."""
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
        self.status = widgets.HTML(self._status_html("⏳ Запуск...", "#f39c12"))

        self._hb_started = time.time()
        self.heartbeat = widgets.HTML(self._heartbeat_html(0))

        # Кнопка-ссылка (появится, когда туннель даст URL)
        self.url_box = widgets.HTML(
            "<i style='color:#888'>Публичная ссылка появится здесь...</i>"
        )

        self.stop_btn = widgets.Button(
            description="Остановить ComfyUI",
            icon="stop",
            button_style="danger",
            layout=widgets.Layout(width="220px", height="42px"),
        )
        self.stop_btn.on_click(self._on_stop_wrapper)

        self.restart_btn = widgets.Button(
            description="Перезапустить",
            icon="refresh",
            button_style="warning",
            layout=widgets.Layout(width="180px", height="42px"),
        )
        self.restart_btn.on_click(self._on_restart_wrapper)

        self.log = widgets.Output(
            layout=widgets.Layout(
                border="1px solid #444", height="360px",
                overflow="auto", padding="6px",
            ),
        )

        buttons = widgets.HBox([self.url_box, self.stop_btn, self.restart_btn])
        self.panel = widgets.VBox([
            self.status,
            self.heartbeat,
            buttons,
            widgets.HTML("<b>Лог:</b>"),
            self.log,
        ])

    def _on_stop_wrapper(self, _btn):
        if self.on_stop_callback:
            self.on_stop_callback()

    def _on_restart_wrapper(self, _btn):
        if self.on_restart_callback:
            self.on_restart_callback()

    @staticmethod
    def _status_html(text, color):
        return f"<h3 style='color:{color}; margin:6px 0'>{text}</h3>"

    @staticmethod
    def _heartbeat_html(elapsed_sec):
        ticks = elapsed_sec // 30
        h, rem = divmod(int(elapsed_sec), 3600)
        m, s = divmod(rem, 60)
        up = f"{h:d}ч {m:02d}м {s:02d}с" if h else f"{m:d}м {s:02d}с"
        return (
            "<div style='font-family:monospace; font-size:13px; color:#2ecc71; "
            "background:#0f1117; border-left:3px solid #2ecc71; "
            "padding:6px 12px; margin:4px 0; border-radius:4px;'>"
            f"💚 keep-alive активен · тик #{ticks} · аптайм {up} · "
            "Kaggle не уснёт</div>"
        )

    def set_status(self, text, color):
        """Обновляет строку статуса над кнопками."""
        self.status.value = self._status_html(text, color)

    # ------------------------------------------------------------------
    # Heartbeat (anti-sleep через виджет)
    # ------------------------------------------------------------------
    def _heartbeat_loop(self):
        """Раз в 30с перерисовывает heartbeat — трафик ядро→браузер."""
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
        """Каждые 5 мин пишет пульс в stdout — Kaggle видит активность
        и не показывает «Are you still there?» даже если вкладка свёрнута."""
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
    # Показ URL туннеля (кнопка-ссылка)
    # ------------------------------------------------------------------
    def show_url(self, url):
        self.url_box.value = (
            f"<a href='{url}' target='_blank' rel='noopener noreferrer' "
            f"style='background:#3498db; color:white; padding:10px 22px; "
            f"text-decoration:none; border-radius:8px; font-size:15px; "
            f"font-weight:bold; display:inline-block; margin-right:12px;'>"
            f"🔗 Открыть ComfyUI</a>"
            f"<div style='font-size:11px; color:#888; margin-top:6px'>{url}</div>"
        )

    def hide_url(self):
        self.url_box.value = "<i style='color:#888'>ComfyUI остановлен.</i>"

    # ------------------------------------------------------------------
    # Лог: дешёвая запись в буфер + троттлинг-перерисовка
    # ------------------------------------------------------------------
    @staticmethod
    def _strip_ansi(text):
        """Удаляет ANSI escape-последовательности."""
        return LogManager._ANSI_RE.sub('', text)

    def print(self, text):
        """Кладёт строки в буфер (дёшево, без I/O в виджет).

        Перерисовка виджета делается отдельным потоком-флешером, чтобы
        поток строк (включая tqdm) не вешал блокнот.

        Одновременно дублирует строки в persistent-файл лога
        (/kaggle/working/comfyui_launcher.log) — пригодится для
        диагностики после того, как виджет очищен или скролл ушёл.

        **ВАЖНО**: Сразу пишет в sys.stdout — гарантирует, что логи
        видны в ячейке даже если виджет не обновляется (проблема с
        прокачкой событий ядра в keep-alive).
        """
        for raw in str(text).split("\n"):
            # tqdm пишет через '\r' без \n — берём только последний сегмент
            seg = raw.split("\r")[-1].rstrip()
            if not seg:
                continue
            seg = self._strip_ansi(seg)
            if not seg:
                continue
            # Прямой вывод в stdout — логи ВСЕГДА видны в ячейке
            sys.stdout.write(f"{seg}\n")
            sys.stdout.flush()
            with self._log_lock:
                self._log_lines.append(seg)
                self._log_dirty = True
                # Дублируем в файл (если открыт)
                if self._log_file:
                    try:
                        self._log_file.write(f"{seg}\n")
                        self._log_file.flush()
                    except OSError:
                        pass

    def _flush_log_now(self):
        """Сбрасывает буфер в виджет лога.

        **ФИКС БАГА**: clear_output(wait=True) вешал поток в фоне — ядро
        не присылало подтверждение очистки. Заменено на wait=False.
        """
        with self._log_lock:
            if not self._log_dirty:
                return
            self._log_dirty = False
            lines = list(self._log_lines)

        if not lines:
            return

        # Если deque вытолкнул старые строки — перерисовываем всё
        needs_redraw = (len(lines) < self._log_rendered) or (self._log_rendered == 0)

        try:
            if needs_redraw:
                # wait=False — не ждём подтверждения ядра (фикс бага)
                self.log.clear_output(wait=False)
                with self.log:
                    for line in lines:
                        print(line, flush=True)
                self._log_rendered = len(lines)
                return

            # Добавляем только новые строки — скролл не сбрасывается
            new_lines = lines[self._log_rendered:]
            if new_lines:
                with self.log:
                    for line in new_lines:
                        print(line, flush=True)
                self._log_rendered = len(lines)
        except Exception:
            pass  # виджет мог быть уже уничтожен

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
        """Читает stdout процесса построчно и отправляет в лог."""
        for line in iter(proc.stdout.readline, ""):
            if line:
                self.print(f"{prefix}{line.rstrip()}")
            if proc.poll() is not None and not line:
                break

    def _run_subprocess(self, cmd, **kwargs):
        """Безопасный запуск subprocess с защитой от KeyboardInterrupt.

        Если пользователь прерывает ячейку (Interrupt), дочерний процесс
        не зависает, а корректно завершается через terminate().
        """
        try:
            preexec_fn = os.setpgrp
        except AttributeError:
            preexec_fn = None  # Windows
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
            preexec_fn=preexec_fn,
            **kwargs,
        )
        return proc

    def stream_script(self, path, label, hint):
        """Запускает .py скрипт и стримит его лог.

        path  — путь к .py;
        label — префикс ([INSTALL] / [NODES]);
        hint  — что подсказать, если файла нет / упал.

        Защита от stale __pycache__: Python-бинарь берётся из sys.executable
        с гарантией, что sys импортирован (если кэш битый — NameError ниже
        ловится и даёт понятную подсказку).
        """
        if not os.path.exists(path):
            raise RuntimeError(f"Установщик не найден: {path}. {hint}")
        self.print(f"[*] Запускаю: {path}")

        # sys.executable — для запуска дочерних скриптов. Если Python
        # подхватил stale .pyc (без import sys), ловим NameError.
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
            # Если юзер нажал Interrupt — не даём процессу зависнуть
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
    # Явный сброс лога (перед остановкой)
    # ------------------------------------------------------------------
    def flush_now(self):
        """Принудительный сброс лога в виджет. Звать перед остановкой."""
        try:
            self._flush_log_now()
        except Exception:
            pass

    def stop(self):
        """Останавливает лог: сбрасывает буфер и закрывает файл.

        Звать из launcher при остановке ComfyUI.
        """
        self.stopped = True
        self.flush_now()
        self._close_log_file()
