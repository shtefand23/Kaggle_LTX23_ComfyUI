#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
launcher.py
=================================================================
Главный оркестратор ComfyUI на Kaggle.

Содержит ComfyLauncher — класс, управляющий жизненным циклом:
  1. Проверка и ремонт окружения (venv, torch, ноды)
  2. Cloudflared туннель
  3. SageAttention-SM75
  4. Запуск ComfyUI + ожидание порта
  5. Кнопки «Остановить» / «Перезапустить»
  6. Keep-alive (anti-sleep)

Пути — ТОЛЬКО из kaggle_env (единый источник правды).
UI и логи — через LogManager (logging_ui.py).
SageAttention — через sage_installer.py.
=================================================================
"""

import asyncio
import os
import re
import socket
import subprocess
import sys
import time
from threading import Thread

# Общий модуль — единый источник путей
import kaggle_env as ke
from kaggle_env import (
    HOME_DIR, COMFY_DIR, VENV_PYTHON,
)

# UI + логи
from logging_ui import LogManager

# SageAttention
import sage_installer

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
    """Держит процессы, виджеты и весь жизненный цикл запуска/остановки."""

    def __init__(self):
        self.comfy_proc = None
        self.tunnel_proc = None
        self.public_url = None
        self.stopped = False
        self._starting = False
        self.sage_ok = False

        # UI + логи
        self.logger = LogManager()
        self.logger.on_stop_callback = self._on_stop
        self.logger.on_restart_callback = self._on_restart

    # ------------------------------------------------------------------
    # Публичная точка входа
    # ------------------------------------------------------------------
    def launch(self):
        from IPython.display import display
        display(self.logger.panel)

        Thread(target=self.logger._heartbeat_loop, daemon=True).start()
        Thread(target=self.logger._stdout_keep_alive, daemon=True).start()
        Thread(target=self.logger._log_flusher, daemon=True).start()
        Thread(target=self._startup, daemon=True).start()

        self._keep_alive()
        return self.logger.panel

    # ------------------------------------------------------------------
    # Запуск (в фоновом потоке)
    # ------------------------------------------------------------------
    def _startup(self):
        self._starting = True
        self.logger.stop_btn.disabled = False
        self.logger.restart_btn.disabled = True
        try:
            self._cleanup_old()
            self._check_git_updates()
            self._check_files()
            self._ensure_cloudflared()
            self._install_sage_attention()
            self._start_comfy()
            self._wait_for_port()
            self._start_tunnel()
        except Exception as e:
            self.logger.set_status(f"❌ Ошибка запуска: {e}", "#e74c3c")
            self.logger.print(f"[ERROR] {e}")
        finally:
            self._starting = False
            self.logger.restart_btn.disabled = False

    # ------------------------------------------------------------------
    # 1. Убиваем старые процессы и чистим блокировки
    # ------------------------------------------------------------------
    def _cleanup_old(self):
        self.logger.print("[*] Очистка старых процессов...")
        for pat in ("main.py", "comfyui", "cloudflared"):
            subprocess.run(["pkill", "-9", "-f", pat], capture_output=True)
        time.sleep(2)
        for f in (f"{COMFY_DIR}/user/comfyui.db",
                  f"{COMFY_DIR}/user/comfyui.db-journal"):
            try:
                if os.path.exists(f):
                    os.remove(f)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # 1b. Проверка обновлений из git-репозитория
    # ------------------------------------------------------------------
    def _check_git_updates(self):
        self.logger.print("[*] Проверяю обновления скриптов (THE-ANGEL-AI)...")
        self.logger.set_status("🔄 Проверка обновлений...", "#f39c12")

        try:
            result = subprocess.run(
                ["git", "-C", _THIS_DIR, "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=10, check=True)
            repo_root = result.stdout.strip()
        except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
            self.logger.print("[*] Это не git-клон — пропускаю проверку обновлений")
            return

        try:
            fetch = subprocess.run(
                ["git", "-C", repo_root, "fetch", "--quiet"],
                capture_output=True, text=True, timeout=30)
            if fetch.returncode != 0:
                self.logger.print(f"[!] git fetch не удался: {fetch.stderr.strip()}")
                return

            status = subprocess.run(
                ["git", "-C", repo_root, "status", "-sb"],
                capture_output=True, text=True, timeout=15)
            behind = "behind" in (status.stdout + status.stderr)

            if not behind:
                self.logger.print("[*] Скрипты обновлены (всё актуально)")
                self.logger.set_status("✅ Скрипты обновлены", "#27ae60")
                return

            self.logger.set_status("⚙️ Скачиваю обновления...", "#f39c12")
            self.logger.print("[*] Найдены обновления — скачиваю...")
            pull = subprocess.run(
                ["git", "-C", repo_root, "pull", "--ff-only"],
                capture_output=True, text=True, timeout=30)
            if pull.returncode != 0:
                self.logger.print(f"[!] git pull не удался: {pull.stderr.strip()}")
                return
            self.logger.print(f"[OK] Скрипты обновлены:\n{pull.stdout.strip()}")
            self.logger.set_status("✅ Скрипты обновлены до последней версии", "#27ae60")
        except subprocess.TimeoutExpired:
            self.logger.print("[!] Таймаут git-операции — пропускаю обновление")
        except Exception as e:
            self.logger.print(f"[!] Ошибка при проверке обновлений: {e}")

    # ------------------------------------------------------------------
    # 2. Проверка файлов и окружения
    # ------------------------------------------------------------------
    def _check_files(self):
        # venv пропал или битый (типично после рестарта сессии Kaggle)
        if not ke.venv_python_ok():
            self.logger.set_status("⚙️ venv нерабочий — чиню Python-окружение...", "#f39c12")
            self.logger.print("[!] venv нерабочий — запускаю kaggle_env.install_python()")
            try:
                was_ok = ke.install_python()
            except Exception as exc:
                self.logger.print(f"[!] install_python() упал: {exc}")
                raise RuntimeError(
                    "Ошибка при установке Python-окружения — смотри лог выше") from exc

            if not ke.venv_python_ok():
                raise RuntimeError("venv так и не заработал — смотри лог выше")

            if not was_ok:
                self.logger.set_status("⚙️ Устанавливаю torch и зависимости ComfyUI...", "#f39c12")
                self.logger.print("[!] venv пересоздан — устанавливаю torch через установщик")
                self.logger.stream_script(INSTALLER, "INSTALL",
                    "Запусти вручную: !python instal/instal_comfyui.py")

        # Если ComfyUI не установлен — авто-установка через instal_comfyui.py.
        # Скрипт ИДЕМПОТЕНТЕН: если всё уже есть — пропустит лишнюю работу.
        if not os.path.exists(f"{COMFY_DIR}/main.py"):
            self.logger.set_status("⚙️ ComfyUI не найден — устанавливаю...", "#f39c12")
            self.logger.print("[!] ComfyUI не найден — запускаю instal_comfyui.py")
            self.logger.stream_script(INSTALLER, "INSTALL",
                "Запусти вручную: !python instal/instal_comfyui.py")
            self.logger.print("[*] ComfyUI установлен")

        self.logger.print("[*] Файлы ComfyUI и рабочий venv на месте")

        # Проверка torch: venv цел, но torch не видит CUDA
        if not ke.torch_cuda_ok():
            self.logger.set_status("⚙️ torch не видит CUDA — устанавливаю...", "#f39c12")
            self.logger.print("[!] torch не видит CUDA — запускаю установщик")
            self.logger.stream_script(INSTALLER, "INSTALL",
                "Запусти вручную: !python instal/instal_comfyui.py")
            self.logger.set_status("⚙️ Устанавливаю зависимости кастомных нод...", "#f39c12")
            self.logger.print("[!] Переустанавливаю зависимости кастомных нод")
            self.logger.stream_script(NODE_INSTALLER, "NODES",
                "Запусти вручную: !python instal/instal_castom_node.py")

        # Кастомные ноды
        self._check_nodes()

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
        url = ("https://github.com/cloudflare/cloudflared/releases/latest/"
               "download/cloudflared-linux-amd64")
        too_small = (os.path.exists(CLOUDFLARED)
                     and os.path.getsize(CLOUDFLARED) < 5_000_000)
        if not os.path.exists(CLOUDFLARED) or too_small:
            if too_small:
                self.logger.print("[*] cloudflared битый/недокачан — качаю заново...")
                try:
                    os.remove(CLOUDFLARED)
                except OSError:
                    pass
            else:
                self.logger.print("[*] Скачиваю cloudflared...")
            subprocess.run(["wget", "-q", url, "-O", CLOUDFLARED], check=True)
        os.chmod(CLOUDFLARED, 0o755)
        self.logger.print("[*] cloudflared готов (+x выставлен)")

    # ------------------------------------------------------------------
    # 3b. SageAttention-SM75 (Turing)
    # ------------------------------------------------------------------
    def _install_sage_attention(self):
        """Устанавливает SageAttention через sage_installer."""
        self.sage_ok = sage_installer.install(
            home_dir=HOME_DIR,
            venv_python=VENV_PYTHON,
            comfy_dir=COMFY_DIR,
            logger=self.logger,
        )
        if self.sage_ok:
            # Инжект SageAttention в workflow
            sage_installer.inject_into_workflows(COMFY_DIR, self.logger)
            self.logger.set_status("SageAttention-SM75 ready", "#27ae60")

    # ------------------------------------------------------------------
    # 4. Запуск ComfyUI
    # ------------------------------------------------------------------
    def _start_comfy(self):
        self.logger.set_status("⏳ Запуск ComfyUI...", "#f39c12")
        if self.sage_ok:
            self.logger.print("[*] Attention: SageAttention-T4 (ComfyUI custom node)")
        else:
            self.logger.print("[*] Attention: --use-split-cross-attention (SageAttention не установлен)")

        comfy_args = [
            VENV_PYTHON, "main.py",
            "--listen", "0.0.0.0",
            "--port", str(PORT),
            "--enable-cors-header", "*",
            "--disable-auto-launch",
            "--preview-method", "auto",
        ]
        if not self.sage_ok:
            comfy_args.append("--use-split-cross-attention")

        self.comfy_proc = subprocess.Popen(
            comfy_args,
            cwd=COMFY_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        Thread(target=self.logger.stream_process,
               args=(self.comfy_proc, "[COMFY] "),
               daemon=True).start()

    # ------------------------------------------------------------------
    # 5. Ожидание порта
    # ------------------------------------------------------------------
    def _wait_for_port(self):
        self.logger.print("[*] Ожидание запуска сервера...")
        start = time.time()
        while True:
            if self.comfy_proc.poll() is not None:
                raise RuntimeError(
                    f"ComfyUI завершился с кодом {self.comfy_proc.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", PORT), timeout=2):
                    break
            except OSError:
                pass
            if time.time() - start > STARTUP_TIMEOUT:
                raise RuntimeError(f"Таймаут запуска ComfyUI ({STARTUP_TIMEOUT}с)")
            time.sleep(2)
        self.logger.set_status("✅ ComfyUI запущен, поднимаю туннель...", "#27ae60")

    # ------------------------------------------------------------------
    # 6. Cloudflare-туннель + парсинг URL
    # ------------------------------------------------------------------
    def _start_tunnel(self):
        self.tunnel_proc = subprocess.Popen(
            [
                CLOUDFLARED, "tunnel", "--no-autoupdate",
                "--protocol", "http2",
                "--url", f"http://127.0.0.1:{PORT}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        start = time.time()
        while time.time() - start < URL_TIMEOUT:
            if self.tunnel_proc.poll() is not None:
                raise RuntimeError("Процесс туннеля завершился")
            line = self.tunnel_proc.stdout.readline()
            if not line:
                continue
            self.logger.print(f"[TUNNEL] {line.rstrip()}")
            m = re.search(r"https://[^\s]+trycloudflare\.com", line)
            if m:
                self.public_url = m.group(0)
                break

        # Остаток логов туннеля — в фон
        Thread(target=self.logger.stream_process,
               args=(self.tunnel_proc, "[TUNNEL] "),
               daemon=True).start()

        if self.public_url:
            self.logger.show_url(self.public_url)
            self.logger.set_status("✅ ComfyUI доступен!", "#27ae60")
        else:
            self.logger.set_status("⚠️ Туннель поднят, но ссылку найти не удалось — "
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
        self.logger.stop_btn.disabled = True
        self._kill_processes()
        self.logger.hide_url()
        self.logger.set_status("🛑 ComfyUI остановлен. Запусти ячейку заново.",
                               "#e74c3c")
        self.logger.print("[*] ComfyUI и туннель остановлены.")
        self.logger.flush_now()

    # ------------------------------------------------------------------
    # Кнопка «Перезапустить»
    # ------------------------------------------------------------------
    def _on_restart(self):
        if self._starting:
            return
        self.logger.restart_btn.disabled = True
        self.logger.set_status("🔄 Перезапуск ComfyUI...", "#f39c12")
        self.logger.print("[*] Перезапуск: гашу старые процессы...")
        self._kill_processes()

        # Сброс состояния под новый запуск
        self.stopped = False
        self.public_url = None
        self.comfy_proc = None
        self.tunnel_proc = None
        self.logger.hide_url()
        self.logger.url_box.value = "<i style='color:#888'>Публичная ссылка появится здесь...</i>"

        # Запускаем заново (в фоне)
        self._starting = False
        Thread(target=self._startup, daemon=True).start()

    # ------------------------------------------------------------------
    # keep-alive: держит ячейку активной
    # ------------------------------------------------------------------
    def _make_kernel_pump(self):
        """Прокачивает события ядра, чтобы кнопки-виджеты отвечали."""
        try:
            try:
                import nest_asyncio
            except ImportError:
                subprocess.run([sys.executable, "-m", "pip", "install", "-q",
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
        """Держит ячейку активной, чтобы Kaggle не усыпил сессию."""
        pump = self._make_kernel_pump()
        if pump is None:
            self.logger.print("[!] Обработку кнопок в keep-alive включить не удалось — "
                        "для остановки используй ⏹ (Interrupt).")
        self.logger.print("[*] keep-alive активен — Kaggle не уснёт. "
                    "Останови кнопкой или ⏹ (Interrupt).")
        try:
            while not self.stopped:
                if pump is not None:
                    try:
                        pump()
                    except Exception:
                        time.sleep(0.2)
                time.sleep(0.05)
        except KeyboardInterrupt:
            self.logger.print("[*] Interrupt — останавливаю ComfyUI и туннель...")
            self._on_stop()
        self.logger.flush_now()
