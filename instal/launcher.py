#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
launcher.py
=================================================================
Главный оркестратор ComfyUI на Kaggle.

Содержит ComfyLauncher — класс, управляющий жизненным циклом:
  1. Проверка и ремонт окружения (venv, torch, ноды)
  2. Cloudflared туннель
  3. Запуск ComfyUI + ожидание порта
  4. Keep-alive (anti-sleep) + HTML-панель

Пути — ТОЛЬКО из kaggle_env (единый источник правды).
UI и логи — через LogManager (logging_ui.py).
Виджеты: widgets.HTML для лога, статуса, heartbeat, URL.
Кнопки: widgets.Button для остановки и перезапуска.
Остановка — кнопка «🛑 Остановить» в панели.
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

# Общий модуль — единый источник путей
import kaggle_env as ke
from kaggle_env import (
    HOME_DIR, COMFY_DIR, VENV_PYTHON,
)

# UI + логи
from logging_ui import LogManager



# Путь к скриптам установщиков
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
INSTALLER      = os.path.join(_THIS_DIR, "instal_comfyui.py")
NODE_INSTALLER = os.path.join(_THIS_DIR, "instal_castom_node.py")

# Таймауты
PORT            = 8188
STARTUP_TIMEOUT = 240   # сек на запуск ComfyUI
URL_TIMEOUT     = 90    # сек на получение ссылки Cloudflare
CLOUDFLARED     = f"{HOME_DIR}/cloudflared"

# Авто-обновление нод
AUTO_UPDATE_NODES = True
AUTO_UPDATE_NODE_REQS = False


class ComfyLauncher:
    """Держит процессы и весь жизненный цикл запуска/остановки."""

    def __init__(self):
        self.comfy_proc = None
        self.tunnel_proc = None
        self.public_url = None
        self.stopped = False
        self._starting = False
        # UI + логи
        self.logger = LogManager()
        self.logger.on_stop_callback = self._on_stop
        self.logger.on_restart_callback = self._on_restart

    # ------------------------------------------------------------------
    # Helpers консольного логирования
    # ------------------------------------------------------------------

    def _log_step(self, name, status=None):
        """Отмечает начало шага: разделитель + таймер + статус.
        Возвращает time.time() для замера длительности."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.logger.print(f"\n{'='*60}")
        self.logger.print(f"  [{ts}] {name}")
        self.logger.print(f"{'='*60}")
        if status:
            self.logger.set_status(status, "#f39c12")
        return time.time()

    def _log_elapsed(self, start, msg="✓ Шаг завершён"):
        """Логирует время, прошедшее с start."""
        elapsed = time.time() - start
        self.logger.print(f"[{msg}] ({elapsed:.1f}с)")

    # ------------------------------------------------------------------
    # Публичная точка входа
    # ------------------------------------------------------------------
    def launch(self):
        # Панель рисуется в __init__ LogManager через display()
        # Все потоки daemon — живут, пока жив kernel.
        # Ячейка НЕ блокируется, kernel обрабатывает on_click кнопок.
        Thread(target=self.logger._heartbeat_loop, daemon=True).start()
        Thread(target=self.logger._stdout_keep_alive, daemon=True).start()
        Thread(target=self._startup, daemon=True).start()

    # ------------------------------------------------------------------
    # Запуск (в фоновом потоке)
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
            self._start_comfy()
            self._wait_for_port()
            self._start_tunnel()
            total = time.time() - _t_startup
            self.logger.print(f"\n{'='*60}")
            self.logger.print(f"  ✅ Полный запуск за {total:.1f}с")
            self.logger.print(f"{'='*60}")
        except Exception as e:
            self._kill_processes()
            self.logger.set_status(f"❌ Ошибка запуска: {e}", "#e74c3c")
            elapsed = time.time() - _t_startup
            self.logger.print(f"\n{'='*60}")
            self.logger.print(f"  ❌ Ошибка на {elapsed:.0f}с: {e}")
            self.logger.print(f"{'='*60}")
            self.logger.print(f"[ERROR] {e}\n{traceback.format_exc()}")
            traceback.print_exc()
        finally:
            self._starting = False

    # ------------------------------------------------------------------
    # 1. Убиваем старые процессы и чистим блокировки
    # ------------------------------------------------------------------
    def _cleanup_old(self):
        t0 = self._log_step("Шаг 1/6: Очистка старых процессов и блокировок")
        total_killed = 0
        for pat in ("main.py", "comfyui", "cloudflared"):
            try:
                pgrep = subprocess.run(
                    ["pgrep", "-f", pat],
                    capture_output=True, text=True)
                if pgrep.returncode == 0 and pgrep.stdout.strip():
                    pids = pgrep.stdout.strip().splitlines()
                    self.logger.print(f"  → {pat}: найдено PID: {', '.join(pids)}")
                    total_killed += len(pids)
                subprocess.run(["pkill", "-9", "-f", pat],
                               capture_output=True)
            except OSError:
                pass
        if total_killed == 0:
            self.logger.print("  → Старых процессов не найдено")
        else:
            self.logger.print(f"  → Убито процессов: {total_killed}")
        time.sleep(2)
        removed = 0
        for f in (f"{COMFY_DIR}/user/comfyui.db",
                  f"{COMFY_DIR}/user/comfyui.db-journal"):
            try:
                if os.path.exists(f):
                    os.remove(f)
                    self.logger.print(f"  → Удалён файл: {os.path.basename(f)}")
                    removed += 1
            except OSError as e:
                self.logger.print(f"  → Не удалён {os.path.basename(f)}: {e}")
        if removed == 0:
            self.logger.print("  → Файлов блокировок нет")
        self._log_elapsed(t0)

    # ------------------------------------------------------------------
    # 1b. Проверка обновлений из git-репозитория
    # ------------------------------------------------------------------
    def _check_git_updates(self):
        t0 = self._log_step("Шаг 2/6: Проверка обновлений скриптов (git)")

        try:
            result = subprocess.run(
                ["git", "-C", _THIS_DIR, "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=10, check=True)
            repo_root = result.stdout.strip()
        except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
            self.logger.print("  → Это не git-клон — пропускаю")
            self._log_elapsed(t0)
            return

        try:
            # Текущая позиция
            branch = subprocess.run(["git", "-C", repo_root, "rev-parse",
                                     "--abbrev-ref", "HEAD"],
                                    capture_output=True, text=True, timeout=5)
            commit = subprocess.run(["git", "-C", repo_root, "rev-parse",
                                     "--short", "HEAD"],
                                    capture_output=True, text=True, timeout=5)
            self.logger.print(f"  → Ветка: {branch.stdout.strip()}")
            self.logger.print(f"  → Коммит: {commit.stdout.strip()}")

            # GIT_TERMINAL_PROMPT=0 — не ждать интерактивного ввода
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
                self.logger.print("  → Актуально, обновлений нет")
                self.logger.set_status("✅ Скрипты обновлены", "#27ae60")
                self._log_elapsed(t0)
                return

            self.logger.print("  → Найдены новые коммиты — git pull...")
            self.logger.set_status("⚙️ Скачиваю обновления...", "#f39c12")
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
            self.logger.print(f"  → Загружено {n} новых коммитов")
            self.logger.set_status("✅ Скрипты обновлены", "#27ae60")
        except subprocess.TimeoutExpired:
            self.logger.print("  → Таймаут git-операции — пропускаю")
        except Exception as e:
            self.logger.print(f"  → Ошибка: {e}")
        self._log_elapsed(t0)

    # ------------------------------------------------------------------
    # 2. Проверка файлов и окружения
    # ------------------------------------------------------------------
    def _check_files(self):
        t0 = self._log_step("Шаг 3/6: Проверка файлов и окружения")

        # --- venv ---
        self.logger.print("  ── Проверка Python-окружения ──")
        if not ke.venv_python_ok():
            self.logger.print("  ❌ venv битый — запускаю install_python()")
            try:
                was_ok = ke.install_python()
            except Exception as exc:
                self.logger.print(f"  ❌ install_python() упал: {exc}")
                raise RuntimeError(
                    "Ошибка при установке Python-окружения") from exc
            if not ke.venv_python_ok():
                raise RuntimeError("venv не заработал — смотри лог выше")
            self.logger.print("  ✅ venv восстановлен")
            if not was_ok:
                self.logger.print("  → venv пересоздан — устанавливаю torch")
                self.logger.stream_script(INSTALLER, "INSTALL",
                    "Запусти вручную: !python instal/instal_comfyui.py")
        else:
            self.logger.print("  ✅ venv в порядке")

        # --- ComfyUI ---
        self.logger.print("  ── Проверка ComfyUI ──")
        if not os.path.exists(f"{COMFY_DIR}/main.py"):
            self.logger.print("  ❌ ComfyUI не найден — авто-установка")
            self.logger.stream_script(INSTALLER, "INSTALL",
                "Запусти вручную: !python instal/instal_comfyui.py")
            self.logger.print("  ✅ ComfyUI установлен")
        else:
            self.logger.print("  ✅ ComfyUI на месте")

        # --- torch / CUDA ---
        self.logger.print("  ── Проверка torch/CUDA ──")
        if not ke.torch_cuda_ok():
            self.logger.print("  ❌ torch не видит CUDA — переустановка")
            self.logger.stream_script(INSTALLER, "INSTALL",
                "Запусти вручную: !python instal/instal_comfyui.py")
            self.logger.print("  → Переустанавливаю зависимости нод")
            self.logger.stream_script(NODE_INSTALLER, "NODES",
                "Запусти вручную: !python instal/instal_castom_node.py")
        else:
            self.logger.print("  ✅ torch/CUDA в порядке")

        # --- Кастомные ноды ---
        self._check_nodes()
        self._log_elapsed(t0)

    # --- 2b. проверка и авто-обновление кастомных нод ---
    def _load_node_names(self):
        """Имена нод из instal_castom_node.py (единый источник правды)."""
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "instal_castom_node", NODE_INSTALLER)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return list(getattr(mod, "CUSTOM_NODES", {}).keys())
        except Exception as e:
            self.logger.print(f"[!] Не смог прочитать список нод ({e}) — пропускаю проверку")
            return None

    def _update_node(self, name, path):
        """git pull одной ноды; при реальном обновлении — переустановка её
        requirements в venv (иначе пропускаем)."""
        res = subprocess.run(
            ["git", "-C", path, "pull", "--ff-only"],
            capture_output=True, text=True)
        out = (res.stdout + res.stderr).strip()
        if res.returncode != 0:
            self.logger.print(f"[NODES] {name}: git pull не удался, пропуск — "
                        f"{out.splitlines()[-1] if out else 'нет вывода'}")
            return
        if "Already up to date" in out or "Already up-to-date" in out:
            return
        self.logger.print(f"[NODES] {name}: обновлён код ↓")
        if not AUTO_UPDATE_NODE_REQS:
            return
        req = os.path.join(path, "requirements.txt")
        if os.path.exists(req):
            subprocess.run(
                ["uv", "pip", "install", "--python", VENV_PYTHON, "-r", req],
                capture_output=True, text=True)

    def _update_existing_nodes(self, names):
        """Обновляет (git pull) все ноды из списка, которые уже на диске."""
        nodes_root = f"{COMFY_DIR}/custom_nodes"
        present = [(n, os.path.join(nodes_root, n)) for n in names
                   if os.path.isdir(os.path.join(nodes_root, n))]
        if not present:
            return
        self.logger.set_status("🔄 Обновляю кастомные ноды...", "#f39c12")
        self.logger.print(f"[*] Авто-обновление нод (git pull): {len(present)} шт.")
        for name, path in present:
            try:
                self._update_node(name, path)
            except Exception as e:
                self.logger.print(f"[NODES] {name}: ошибка обновления ({e}), пропуск")
        self.logger.print("[*] Обновление нод завершено")

    def _check_nodes(self):
        if not os.path.exists(NODE_INSTALLER):
            self.logger.print("[!] instal_castom_node.py не найден — пропускаю ноды")
            return
        names = self._load_node_names()
        if names is None:
            return
        nodes_root = f"{COMFY_DIR}/custom_nodes"
        missing = [n for n in names
                   if not os.path.exists(os.path.join(nodes_root, n))]

        if missing:
            self.logger.set_status(
                f"⚙️ Доустанавливаю кастомные ноды ({len(missing)})...", "#f39c12")
            self.logger.print(f"[!] Не хватает нод: {', '.join(missing)} — авто-установка")
            self.logger.stream_script(NODE_INSTALLER, "NODES",
                "Запусти вручную: !python instal/instal_castom_node.py")
            self.logger.print("[*] Кастомные ноды доустановлены и обновлены")
            return

        if AUTO_UPDATE_NODES:
            self._update_existing_nodes(names)
        else:
            self.logger.print("[*] Кастомные ноды на месте (авто-обновление выключено)")

    # ------------------------------------------------------------------
    # 3. cloudflared
    # ------------------------------------------------------------------
    def _ensure_cloudflared(self):
        t0 = self._log_step("Шаг 4/6: Cloudflared (туннель)")

        url = ("https://github.com/cloudflare/cloudflared/releases/latest/"
               "download/cloudflared-linux-amd64")
        if not os.path.exists(CLOUDFLARED):
            self.logger.print("  → Не найден — скачиваю...")
            subprocess.run(["wget", "-q", url, "-O", CLOUDFLARED], check=True)
            size_mb = os.path.getsize(CLOUDFLARED) / 1024 / 1024
            self.logger.print(f"  → Скачан: {size_mb:.1f} MB")
        else:
            size_mb = os.path.getsize(CLOUDFLARED) / 1024 / 1024
            self.logger.print(f"  → Уже есть: {size_mb:.1f} MB")
            if size_mb < 5:
                self.logger.print("  → Размер подозрительно мал — качаю заново")
                try:
                    os.remove(CLOUDFLARED)
                except OSError:
                    pass
                subprocess.run(["wget", "-q", url, "-O", CLOUDFLARED], check=True)
                size_mb = os.path.getsize(CLOUDFLARED) / 1024 / 1024
                self.logger.print(f"  → Скачан: {size_mb:.1f} MB")

        os.chmod(CLOUDFLARED, 0o755)
        self.logger.print("  → Права доступа: 755 (+x)")
        self._log_elapsed(t0)

    # ------------------------------------------------------------------
    # 4. Запуск ComfyUI
    # ------------------------------------------------------------------
    def _start_comfy(self):
        self._log_step("Шаг 5/6: Запуск ComfyUI", status="⏳ Запуск ComfyUI...")
        self.logger.print("  → Режим: split-cross-attention (экономия VRAM на T4)")

        comfy_args = [
            VENV_PYTHON, "main.py",
            "--listen", "0.0.0.0",
            "--port", str(PORT),
            "--enable-cors-header", "*",
            "--disable-auto-launch",
            # --use-split-cross-attention — стандартный флаг ComfyUI
            # для экономии VRAM на T4. Не «ускорение», а совместимость.
            # Без него дефолтный attention жрёт больше памяти, и Kaggle
            # OOM-killer убивает процесс (SIGKILL -9).
            "--use-split-cross-attention",
        ]

        cmd_str = " ".join(comfy_args)
        self.logger.print(f"  → Команда: {cmd_str}")

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
    # 5. Ожидание порта
    # ------------------------------------------------------------------
    def _wait_for_port(self):
        self.logger.print(f"\n{'─'*40}")
        self.logger.print("  Ожидание запуска ComfyUI...")
        start = time.time()
        last_report = 0
        while True:
            if self.comfy_proc.poll() is not None:
                raise RuntimeError(
                    f"ComfyUI завершился с кодом {self.comfy_proc.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", PORT), timeout=2):
                    break
            except OSError:
                pass
            elapsed = time.time() - start
            if elapsed > STARTUP_TIMEOUT:
                raise RuntimeError(f"Таймаут ({STARTUP_TIMEOUT}с)")
            if elapsed - last_report >= 10:
                self.logger.print(f"  ⏳ {elapsed:.0f}с прошло (таймаут {STARTUP_TIMEOUT}с)")
                last_report = elapsed
            time.sleep(2)
        elapsed = time.time() - start
        self.logger.print(f"  ✅ ComfyUI запущен за {elapsed:.1f}с")
        self.logger.set_status("✅ ComfyUI запущен, поднимаю туннель...", "#27ae60")

    # ------------------------------------------------------------------
    # 6. Cloudflare-туннель + парсинг URL
    # ------------------------------------------------------------------
    def _read_tunnel_output(self, url_found: Event):
        """Читает stdout туннеля в фоне, ищет URL.

        Вынесено в отдельный поток, чтобы блокирующий readline()
        не мешал таймауту _start_tunnel().
        """
        try:
            for line in iter(self.tunnel_proc.stdout.readline, ""):
                if line:
                    self.logger.print(f"[TUNNEL] {line.rstrip()}")
                    m = re.search(r"https://[^\s]+trycloudflare\.com", line)
                    if m:
                        self.public_url = m.group(0)
                        url_found.set()
                if self.tunnel_proc.poll() is not None:
                    break
        except (OSError, ValueError):
            pass

    def _start_tunnel(self):
        self._log_step("Шаг 6/6: Cloudflare Tunnel", status="🔄 Поднимаю туннель...")

        cmd = [
            CLOUDFLARED, "tunnel", "--no-autoupdate",
            "--protocol", "http2",
            "--url", f"http://127.0.0.1:{PORT}",
        ]
        self.logger.print(f"  → Команда: {' '.join(cmd)}")

        self.tunnel_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.logger.print(f"  → PID: {self.tunnel_proc.pid}")

        # Читаем stdout туннеля в фоновом потоке — неблокирующий таймаут
        url_found = Event()
        reader = Thread(
            target=self._read_tunnel_output,
            args=(url_found,),
            daemon=True,
        )
        reader.start()

        # Ждём URL с таймаутом
        start = time.time()
        found = url_found.wait(timeout=URL_TIMEOUT)
        elapsed = time.time() - start

        if not found and self.tunnel_proc.poll() is not None:
            raise RuntimeError("Процесс туннеля завершился, URL не получен")

        if self.public_url:
            self.logger.print(f"  ✅ Туннель получен за {elapsed:.1f}с")
            self.logger.show_url(self.public_url)
            self.logger.set_status("✅ ComfyUI доступен!", "#27ae60")
        else:
            self.logger.set_status("⚠️ Туннель поднят, но ссылка не найдена — "
                                   "проверь лог", "#f39c12")

    # ------------------------------------------------------------------
    # Завершение процессов
    # ------------------------------------------------------------------
    def _kill_processes(self):
        for proc in (self.tunnel_proc, self.comfy_proc):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
        for pat in ("main.py", "cloudflared"):
            subprocess.run(["pkill", "-9", "-f", pat], capture_output=True)

    # ------------------------------------------------------------------
    # Кнопка «Остановить»
    # ------------------------------------------------------------------
    def _on_stop(self):
        if self.stopped:
            return
        self.stopped = True
        self.logger.set_status("⏳ Останавливаю ComfyUI...", "#f39c12")
        self.logger.disable_stop_btn()
        self._kill_processes()
        self.logger.hide_url()
        self.logger.set_status("🛑 ComfyUI остановлен. Нажми «Перезапустить».",
                               "#e74c3c")
        self.logger.print("[*] ComfyUI и туннель остановлены.")

    # ------------------------------------------------------------------
    # Кнопка «Перезапустить»
    # ------------------------------------------------------------------
    def _on_restart(self):
        if self._starting:
            return
        self.logger.disable_restart_btn()
        self.logger.set_status("🔄 Перезапуск ComfyUI...", "#f39c12")
        self.logger.print("[*] Перезапуск: гашу старые процессы...")
        self._kill_processes()
        # Сброс состояния под новый запуск
        self.stopped = False
        self.public_url = None
        self.comfy_proc = None
        self.tunnel_proc = None
        self.logger.hide_url()
        self.logger.enable_stop_btn()
        Thread(target=self._startup, daemon=True).start()
