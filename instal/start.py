#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
start.py
=================================================================
ШАГ 3 из 3. Запускает ComfyUI + Cloudflare-туннель и рисует под
ячейкой панель управления.

Поведение (важно для Kaggle):
  * Ячейка РАБОТАЕТ ПОСТОЯННО (keep-alive), пока пользователь сам её не
    остановит. Это держит kernel «активным», иначе Kaggle через ~40 мин
    бездействия усыпляет сессию и она падает. Запуск идёт в фоновом потоке,
    а основной поток ячейки крутит keep-alive цикл и при этом ПРОКАЧИВАЕТ
    очередь сообщений ядра — кнопки-виджеты остаются живыми.
  * Кнопки под ячейкой:
        — «🔗 Открыть ComfyUI»  (публичная ссылка Cloudflare)
        — «🛑 Остановить ComfyUI» (гасит процессы и завершает ячейку)
        — «🔄 Перезапустить»     (перезапуск без рестарта ядра)
    Остановить можно и кнопкой, и через ⏹ (Interrupt) в тулбаре Kaggle.
  * Лог ComfyUI/туннеля выводится ОГРАНИЧЕННО и С ТРОТТЛИНГОМ (последние
    N строк, обновление раз в ~0.5с). Раньше каждая строка отдельно дёргала
    виджет → DOM раздувался и блокнот/браузер зависали.

Скорость на T4:
  * SageAttention-SM75-path (github.com/XUANNISSAN/SageAttention-SM75-path):
    форк с поддержкой Turing (sm_75) — INT8 QK + FP16 PV через CUDA.
    Компилируется в рантайме, даёт ~1.2-1.5x к attention.
    Если установка не удалась — fallback на --use-split-cross-attention.
  * smart-memory НЕ отключаем — модель кэшируется в VRAM между
    генерациями, повторный прогон быстрее.

Запуск (в блокноте):  %run instal/start.py

Перед стартом проверяет окружение. Если venv пропал или стал нерабочим
(битый симлинк после рестарта сессии Kaggle) — АВТОМАТИЧЕСКИ перезапускает
instal_comfyui.py, чтобы пересоздать venv и переустановить torch.
=================================================================
"""

import html
import os
import re
import socket
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from threading import Lock, Thread

import ipywidgets as widgets
from IPython.display import display

# Общий модуль рядом с этим файлом — единый источник правды (пути, uv, venv).
# Его импорт сразу настраивает окружение uv: ставит UV_* env-переменные и
# добавляет /kaggle/working/bin в PATH. БЕЗ этого `uv pip install` ниже падал
# после рестарта сессии (uv не находился в PATH).
try:
    _KE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:                       # __file__ не задан (редкий случай %run)
    _KE_DIR = "/kaggle/working/instal"
sys.path.insert(0, _KE_DIR)
import kaggle_env as ke
ke.setup_env()

# ----------------------------------------------------------------------
# Пути и параметры
# ----------------------------------------------------------------------
HOME_DIR    = "/kaggle/working"
COMFY_DIR   = f"{HOME_DIR}/ComfyUI"
VENV_PYTHON = f"{HOME_DIR}/venv/bin/python"
UV_PYTHON_DIR = f"{HOME_DIR}/uv-python"   # персистентный базовый CPython (см. instal_comfyui.py)
UV_LOCAL_DIR  = f"{HOME_DIR}/bin"         # персистентный бинарник uv (standalone)
CLOUDFLARED = f"{HOME_DIR}/cloudflared"
PORT        = 8188
STARTUP_TIMEOUT = 240   # сек на запуск ComfyUI
URL_TIMEOUT     = 90    # сек на получение ссылки Cloudflare

# Авто-обновление кастомных нод при старте (git pull всех нод из списка).
# Если очередное обновление ноды что-то сломало — поставь False, тогда ноды
# только доустанавливаются (отсутствующие), но не обновляются.
AUTO_UPDATE_NODES = True

# Переустанавливать ли requirements обновлённой ноды в ОБЩИЙ venv.
# По умолчанию ВЫКЛ: реинсталл node-requirements в общий venv может перетереть
# torch/transformers/numpy и сломать другие ноды (классика — GGUF перестаёт
# импортироваться → KeyError 'unet_gguf'/'clip_gguf' у MultiGPU). Обновляем
# только КОД ноды. Если ноде после апдейта реально нужны новые зависимости —
# поставь вручную или перезапусти instal_castom_node.py.
AUTO_UPDATE_NODE_REQS = False

# Логи: ограничение буфера и троттлинг обновлений виджета — против зависания.
LOG_MAX_LINES = 300     # сколько последних строк держим в логе
LOG_FLUSH_SEC = 0.5     # как часто перерисовываем виджет лога

# Путь к установщику ШАГА 1 — берём рядом с этим файлом, не завися от cwd.
# (При `%run instal/start.py` __file__ указывает на instal/start.py.)
try:
    _THIS_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:                       # на всякий случай, если __file__ не задан
    _THIS_DIR = os.path.join(HOME_DIR, "instal")
INSTALLER      = os.path.join(_THIS_DIR, "instal_comfyui.py")
NODE_INSTALLER = os.path.join(_THIS_DIR, "instal_castom_node.py")


class ComfyLauncher:
    """Держит процессы, виджеты и весь жизненный цикл запуска/остановки."""

    def __init__(self):
        self.comfy_proc = None
        self.tunnel_proc = None
        self.public_url = None
        self.stopped = False
        self._starting = False   # идёт ли сейчас запуск (блокирует кнопки)

        # Буфер лога (ограниченный) + троттлинг перерисовки виджета.
        self._log_lines = deque(maxlen=LOG_MAX_LINES)
        self._log_lock = Lock()
        self._log_dirty = False

        self._build_ui()

    # ------------------------------------------------------------------
    # UI: статус, кнопки, лог
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.status = widgets.HTML(self._status_html("⏳ Запуск...", "#f39c12"))

        # Heartbeat-тик: одна живая строка над кнопками. Обновляется раз в 30с
        # ОТДЕЛЬНЫМ потоком и шлёт трафик ядро→браузер — Kaggle видит активность
        # и не усыпляет сессию через ~40 мин «тишины». Это и есть anti-sleep маяк.
        self._hb_started = time.time()
        self.heartbeat = widgets.HTML(self._heartbeat_html(0))

        # Кнопка-ссылка появится, когда туннель отдаст URL.
        self.url_box = widgets.HTML(
            "<i style='color:#888'>Публичная ссылка появится здесь...</i>"
        )

        self.stop_btn = widgets.Button(
            description="Остановить ComfyUI",
            icon="stop",
            button_style="danger",
            layout=widgets.Layout(width="220px", height="42px"),
        )
        self.stop_btn.on_click(self._on_stop_click)

        self.restart_btn = widgets.Button(
            description="Перезапустить",
            icon="refresh",
            button_style="warning",
            layout=widgets.Layout(width="180px", height="42px"),
        )
        self.restart_btn.on_click(self._on_restart_click)

        # Лог — обычный HTML-виджет, который мы ПОЛНОСТЬЮ перерисовываем раз в
        # ~0.5с (а не дёргаем на каждую строку). Содержимое ограничено
        # LOG_MAX_LINES строками — DOM не раздувается, браузер не виснет.
        self.log = widgets.HTML(
            value=self._log_html([]),
            layout=widgets.Layout(
                border="1px solid #444", height="360px",
                overflow="auto", padding="0",
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

    @staticmethod
    def _status_html(text, color):
        return f"<h3 style='color:{color}; margin:6px 0'>{text}</h3>"

    @staticmethod
    def _heartbeat_html(elapsed_sec):
        """Одна живая строка-маяк: пульс + тики + аптайм сессии."""
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

    def _heartbeat_loop(self):
        """Раз в 30с перерисовывает heartbeat-строку (трафик ядро→браузер =
        видимая активность для Kaggle). Крутится, пока ячейку не остановили."""
        while not self.stopped:
            try:
                self.heartbeat.value = self._heartbeat_html(
                    time.time() - self._hb_started)
            except Exception:
                pass
            for _ in range(30):           # спим 30с, но реагируем на стоп быстро
                if self.stopped:
                    return
                time.sleep(1)

    def _stdout_keep_alive(self):
        """Каждые 5 мин пишет пульс в stdout — Kaggle видит активность
        и не показывает 'Are you still there?' даже если вкладка свёрнута.

        В отличие от _heartbeat_loop (который дёргает IPython-виджет),
        print(flush=True) гарантированно отправляет текст на сервер Kaggle
        и не зависит от браузера/виджетов."""
        print("\n🔒 [ЗАЩИТА] Система защиты Kaggle активирована!", flush=True)
        print("🔒 [ЗАЩИТА] Буду отправлять пульс каждые 5 минут\n", flush=True)
        while not self.stopped:
            for _ in range(300):
                if self.stopped:
                    return
                time.sleep(1)
            now = datetime.now().strftime("%H:%M:%S")
            print(f"💓 [{now}] ComfyUI активен, ожидание запроса...", flush=True)

    def _set_status(self, text, color):
        self.status.value = self._status_html(text, color)

    @staticmethod
    def _log_html(lines):
        body = html.escape("\n".join(lines))
        return (
            "<pre style='margin:0; padding:6px; white-space:pre-wrap; "
            "word-break:break-word; background:#0f1117; color:#ddd; "
            "font-family:monospace; font-size:12px; line-height:1.35; "
            "min-height:100%;'>" + body + "</pre>"
        )

    # ------------------------------------------------------------------
    # Лог: дешёвая запись в буфер из любого потока + троттлинг-перерисовка
    # ------------------------------------------------------------------
    def _print(self, text):
        """Кладёт строки в буфер (дёшево, без I/O в виджет).

        Перерисовка виджета делается отдельным потоком-флешером, чтобы поток
        строк от ComfyUI/туннеля (включая tqdm) не вешал блокнот.
        """
        for raw in str(text).split("\n"):
            # tqdm/прогресс пишут через '\r' без перевода строки — берём только
            # последний сегмент, иначе бар копится одной гигантской строкой.
            seg = raw.split("\r")[-1].rstrip()
            if seg == "":
                continue
            with self._log_lock:
                self._log_lines.append(seg)
                self._log_dirty = True

    def _flush_log_now(self):
        with self._log_lock:
            if not self._log_dirty:
                return
            self._log_dirty = False
            lines = list(self._log_lines)
        self.log.value = self._log_html(lines)

    def _log_flusher(self):
        """Раз в LOG_FLUSH_SEC перерисовывает виджет лога, если он изменился."""
        while True:
            time.sleep(LOG_FLUSH_SEC)
            try:
                self._flush_log_now()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Публичная точка входа
    # ------------------------------------------------------------------
    def launch(self):
        display(self.panel)                       # панель появляется под ячейкой
        Thread(target=self._heartbeat_loop, daemon=True).start()   # anti-sleep маяк (виджет)
        Thread(target=self._stdout_keep_alive, daemon=True).start()  # защита от "Are you there?" (stdout)
        Thread(target=self._log_flusher, daemon=True).start()
        Thread(target=self._startup, daemon=True).start()   # запуск в фоне
        # Блокируем ячейку keep-alive циклом — kernel остаётся активным, Kaggle
        # не усыпляет сессию. Цикл завершится по «Остановить» или Interrupt.
        self._keep_alive()
        return self.panel

    # ------------------------------------------------------------------
    # Поток логов процесса -> лог-виджет
    # ------------------------------------------------------------------
    def _stream(self, proc, prefix):
        for line in iter(proc.stdout.readline, ""):
            if line:
                self._print(f"{prefix}{line.rstrip()}")
            if proc.poll() is not None and not line:
                break

    # ------------------------------------------------------------------
    # Главная последовательность запуска (в фоновом потоке)
    # ------------------------------------------------------------------
    def _startup(self):
        self._starting = True
        self.stop_btn.disabled = False
        self.restart_btn.disabled = True   # нельзя жать «Перезапустить» во время запуска
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
            self._set_status(f"❌ Ошибка запуска: {e}", "#e74c3c")
            self._print(f"[ERROR] {e}")
        finally:
            self._starting = False
            self.restart_btn.disabled = False   # запуск завершён — перезапуск доступен

    # --- 1. убиваем старые процессы и чистим блокировки ----------------
    def _cleanup_old(self):
        self._print("[*] Очистка старых процессов...")
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

    # --- 1b. проверка обновлений из git-репозитория --------------------
    def _check_git_updates(self):
        """Проверяет обновления скриптов из git-репозитория THE-ANGEL-AI.

        Если instal/ — это git-клон, делает fetch + pull с ветки GIT_BRANCH.
        Если обновления есть — перекачивает файлы и сообщает в лог.
        Если это не git-репозиторий или нет доступа — пропускает молча.
        """
        self._print("[*] Проверяю обновления скриптов (THE-ANGEL-AI)...")
        self._set_status("🔄 Проверка обновлений...", "#f39c12")

        # Проверяем, что _THIS_DIR — git-репозиторий.
        git_dir = os.path.join(_THIS_DIR, ".git")
        if not os.path.isdir(git_dir):
            # Это не git-клон (может, скрипты скопированы вручную) — пропускаем.
            self._print("[*] Это не git-клон — пропускаю проверку обновлений")
            return

        try:
            # Fetch + pull: забираем последние коммиты.
            fetch = subprocess.run(
                ["git", "-C", _THIS_DIR, "fetch", "--quiet"],
                capture_output=True, text=True, timeout=30)
            if fetch.returncode != 0:
                self._print(f"[!] git fetch не удался: {fetch.stderr.strip()}")
                return

            # Сравниваем локальный HEAD с origin/BRANCH — есть ли разница?
            status = subprocess.run(
                ["git", "-C", _THIS_DIR, "status", "-sb"],
                capture_output=True, text=True, timeout=15)
            behind = "behind" in (status.stdout + status.stderr)

            if not behind:
                self._print("[*] Скрипты обновлены (всё актуально)")
                self._set_status("✅ Скрипты обновлены", "#27ae60")
                return

            self._set_status("⚙️ Скачиваю обновления...", "#f39c12")
            self._print("[*] Найдены обновления — скачиваю...")
            pull = subprocess.run(
                ["git", "-C", _THIS_DIR, "pull", "--ff-only"],
                capture_output=True, text=True, timeout=30)
            if pull.returncode != 0:
                self._print(f"[!] git pull не удался: {pull.stderr.strip()}")
                return
            self._print(f"[OK] Скрипты обновлены:\n{pull.stdout.strip()}")
            self._set_status("✅ Скрипты обновлены до последней версии", "#27ae60")
        except subprocess.TimeoutExpired:
            self._print("[!] Таймаут git-операции — пропускаю обновление")
        except Exception as e:
            self._print(f"[!] Ошибка при проверке обновлений: {e}")

    # --- 2. проверки файлов -------------------------------------------
    def _venv_python_ok(self):
        """venv цел только если его python реально запускается.

        Делегируем в общий модуль kaggle_env (единый источник правды) —
        проверка идёт реальным запуском, а не os.path.exists (после рестарта
        Kaggle симлинк цел, но теряет +x).
        """
        return ke.venv_python_ok()

    def _repair_venv_perms(self):
        """Дёшево чинит частую поломку после рестарта Kaggle: слетевший бит +x.

        Делегируем в kaggle_env.repair_venv_perms() — он возвращает +x
        интерпретатору venv, бинарю uv и базовому CPython, не пересоздавая
        venv и не переустанавливая torch. Возвращает True, если venv заработал.
        """
        ok = ke.repair_venv_perms()
        if ok:
            self._print("[*] Вернул бит +x интерпретатору venv/uv-python "
                        "(после рестарта слетал)")
        return ok

    def _run_script(self, path, label, hint):
        """Запускает установщик-скрипт, стримя его лог в виджет.

        path  — путь к .py (INSTALLER или NODE_INSTALLER);
        label — префикс строк в логе ([INSTALL] / [NODES]);
        hint  — что подсказать, если файла нет / упал.
        """
        if not os.path.exists(path):
            raise RuntimeError(f"Установщик не найден: {path}. {hint}")
        self._print(f"[*] Запускаю: {path}")
        proc = subprocess.Popen(
            [sys.executable, path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        for line in iter(proc.stdout.readline, ""):
            if line:
                self._print(f"[{label}] {line.rstrip()}")
            if proc.poll() is not None and not line:
                break
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(
                f"{path} завершился с кодом {proc.returncode}. {hint}")

    def _run_installer(self):
        """Запускает instal_comfyui.py (пересоздаёт venv, ставит torch)."""
        self._run_script(
            INSTALLER, "INSTALL",
            "Запусти вручную: !python instal/instal_comfyui.py")

    def _run_node_installer(self):
        """Запускает instal_castom_node.py (ставит кастомные ноды + симлинки)."""
        self._run_script(
            NODE_INSTALLER, "NODES",
            "Запусти вручную: !python instal/instal_castom_node.py")

    def _check_files(self):
        # venv пропал или битый (типично после рестарта сессии Kaggle).
        if not self._venv_python_ok():
            # Этап 1: дёшево вернуть слетевший бит +x (частая поломка
            # после рестарта). Если помогло — venv цел, torch не трогаем.
            self._set_status("⚙️ venv нерабочий — пробую быстрый +x-ремонт...",
                             "#f39c12")
            self._print("[!] venv нерабочий — пробую быстрый +x-ремонт перед "
                        "полной переустановкой")
            if self._repair_venv_perms():
                self._print("[*] venv починен возвратом +x — переустановка "
                            "не нужна")
                return

            # Этап 2: +x не помог — может, обновилось ядро Kaggle (libc/kernel
            # несовместимы со старым CPython). Пробуем удалить старый CPython
            # и установить свежий через uv.
            self._set_status("⚙️ +x не помог — обновляю базовый CPython...",
                             "#f39c12")
            self._print("[!] +x-ремонт не помог — удаляю старый CPython и "
                        "ставлю свежий (совместимый с этим ядром Kaggle)")
            try:
                ke.repair_base_python_via_uv()
                # NB: эта функция НЕ чинит venv (старый symlink битый).
                # Она только готовит свежий CPython. Продолжаем переустановкой.
            except Exception as exc:
                self._print(f"[!] repair_base_python_via_uv упал: {exc}")

            # Этап 3: пересоздаём venv с новым CPython через установщик
            # ШАГА 1 (uv venv --clear + reinstall torch из кэша).
            # Пакеты переставятся из uv-кэша (быстро, torch уже скачан).
            self._set_status("⚙️ Переустанавливаю venv через установщик...",
                             "#f39c12")
            self._print("[!] CPython-ремонт не помог — авто-переустановка venv")
            self._run_installer()
            if not self._venv_python_ok():
                raise RuntimeError(
                    "venv так и не заработал после установщика — смотри лог выше"
                )
            # После пересоздания venv все пакеты (включая зависимости
            # кастомных нод) пропали — переустанавливаем их сразу.
            self._set_status("⚙️ Переустанавливаю зависимости кастомных нод...",
                             "#f39c12")
            self._print("[!] venv пересоздан — переустанавливаю зависимости "
                        "кастомных нод (иначе упадут с ImportError)")
            self._run_node_installer()

        for path, msg in (
            (COMFY_DIR, "ComfyUI не найден — запусти instal/instal_comfyui.py"),
            (f"{COMFY_DIR}/main.py", "main.py не найден"),
        ):
            if not os.path.exists(path):
                raise RuntimeError(msg)
        self._print("[*] Файлы ComfyUI и рабочий venv на месте")

        # Кастомные ноды (ШАГ 2). Если каких-то нод из списка нет —
        # автоматически доустанавливаем через instal_castom_node.py.
        self._check_nodes()

    # --- 2b. проверка и авто-обновление кастомных нод -----------------
    def _load_node_names(self):
        """Имена нод из instal_castom_node.py (единый источник правды).

        Грузим установщик как модуль и читаем CUSTOM_NODES, не запуская main().
        Возвращает список имён или None, если прочитать не вышло.
        """
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "instal_castom_node", NODE_INSTALLER)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return list(getattr(mod, "CUSTOM_NODES", {}).keys())
        except Exception as e:
            self._print(f"[!] Не смог прочитать список нод ({e}) — пропускаю проверку")
            return None

    def _update_node(self, name, path):
        """git pull одной ноды; при реальном обновлении — переустановка её
        requirements в venv (иначе пропускаем, чтобы не тормозить старт)."""
        res = subprocess.run(
            ["git", "-C", path, "pull", "--ff-only"],
            capture_output=True, text=True)
        out = (res.stdout + res.stderr).strip()
        if res.returncode != 0:
            self._print(f"[NODES] {name}: git pull не удался, пропуск — "
                        f"{out.splitlines()[-1] if out else 'нет вывода'}")
            return
        if "Already up to date" in out or "Already up-to-date" in out:
            return                                   # уже свежая — ничего не делаем
        self._print(f"[NODES] {name}: обновлён код ↓")
        # Реинсталл requirements в ОБЩИЙ venv по умолчанию ВЫКЛ — он может
        # перетереть torch/transformers/numpy и сломать другие ноды.
        if not AUTO_UPDATE_NODE_REQS:
            return
        req = os.path.join(path, "requirements.txt")
        if os.path.exists(req):
            # uv ставит requirements в наш venv (как в instal_castom_node.py).
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
        self._set_status("🔄 Обновляю кастомные ноды...", "#f39c12")
        self._print(f"[*] Авто-обновление нод (git pull): {len(present)} шт.")
        for name, path in present:
            try:
                self._update_node(name, path)
            except Exception as e:
                self._print(f"[NODES] {name}: ошибка обновления ({e}), пропуск")
        self._print("[*] Обновление нод завершено")

    def _check_nodes(self):
        if not os.path.exists(NODE_INSTALLER):
            self._print("[!] instal_castom_node.py не найден — пропускаю ноды")
            return
        names = self._load_node_names()
        if names is None:
            return
        nodes_root = f"{COMFY_DIR}/custom_nodes"
        missing = [n for n in names
                   if not os.path.exists(os.path.join(nodes_root, n))]

        # Не хватает нод — ставим полным установщиком. Он попутно делает git pull
        # уже существующих и пересоздаёт симлинки, так что обновление включено.
        if missing:
            self._set_status(
                f"⚙️ Доустанавливаю кастомные ноды ({len(missing)})...", "#f39c12")
            self._print(f"[!] Не хватает нод: {', '.join(missing)} — авто-установка")
            self._run_node_installer()
            self._print("[*] Кастомные ноды доустановлены и обновлены")
            return

        # Все ноды на месте — просто обновляем их (если включено).
        if AUTO_UPDATE_NODES:
            self._update_existing_nodes(names)
        else:
            self._print("[*] Кастомные ноды на месте (авто-обновление выключено)")

    # --- 3. cloudflared ------------------------------------------------
    def _ensure_cloudflared(self):
        """Готовит бинарь cloudflared.

        Файл переживает рестарт сессии Kaggle, НО теряет бит исполнения
        (а иногда оказывается недокачанным/битым). Раньше при существующем
        файле скачивание и chmod пропускались → запуск падал с
        '[Errno 13] Permission denied'. Теперь: качаем, если файла нет или он
        подозрительно мал, и ВСЕГДА заново выставляем +x.
        """
        url = ("https://github.com/cloudflare/cloudflared/releases/latest/"
               "download/cloudflared-linux-amd64")
        too_small = (os.path.exists(CLOUDFLARED)
                     and os.path.getsize(CLOUDFLARED) < 5_000_000)
        if not os.path.exists(CLOUDFLARED) or too_small:
            if too_small:
                self._print("[*] cloudflared битый/недокачан — качаю заново...")
                try:
                    os.remove(CLOUDFLARED)
                except OSError:
                    pass
            else:
                self._print("[*] Скачиваю cloudflared...")
            subprocess.run(["wget", "-q", url, "-O", CLOUDFLARED], check=True)
        # +x обязательно — после рестарта Kaggle бит исполнения теряется.
        os.chmod(CLOUDFLARED, 0o755)
        self._print("[*] cloudflared готов (+x выставлен)")



    # --- 3b. SageAttention-SM75 (Turing) -----------------------------
    SAGE_SRC = f"{HOME_DIR}/sageattention-sm75"

    def _install_sage_attention(self):
        """Клонирует и собирает SageAttention-SM75-path с поддержкой Turing.

        Компилирует CUDA-ядро `sageattn_qk_int8_pv_fp16_cuda_sm75`.
        Идемпотентно: если пакет уже импортируется — пропускает.
        self.sage_ok = True/False — результат для динамического выбора флага.

        Использует клонирование + local install, чтобы видеть полный лог
        ошибок при компиляции CUDA.
        """
        self._print("[*] Проверяю SageAttention-SM75 (Turing)...")
        self.sage_ok = False

        # Уже установлен?
        check = subprocess.run(
            [VENV_PYTHON, "-c", "import sageattention"],
            capture_output=True, text=True, timeout=15)
        if check.returncode == 0:
            self._print("[*] SageAttention уже установлен (пропуск)")
            self.sage_ok = True
            return

        self._set_status("⚙️ Устанавливаю SageAttention-SM75...", "#f39c12")
        repo_url = "https://github.com/XUANNISSAN/SageAttention-SM75-path.git"

        # Шаг 1: обновляем build-зависимости
        self._print("[*] Обновляю setuptools + wheel...")
        subprocess.run(
            [VENV_PYTHON, "-m", "pip", "install", "--upgrade",
             "setuptools", "wheel"],
            capture_output=True, text=True, timeout=120)

        # Шаг 2: клонируем репозиторий (если ещё не склонирован)
        if os.path.isdir(self.SAGE_SRC):
            self._print("[*] Репозиторий уже склонирован — делаю git pull...")
            subprocess.run(["git", "-C", self.SAGE_SRC, "pull", "--ff-only"],
                           capture_output=True, text=True, timeout=60)
        else:
            self._print("[*] Клонирую SageAttention-SM75-path...")
            clone = subprocess.run(
                ["git", "clone", repo_url, self.SAGE_SRC],
                capture_output=True, text=True, timeout=120)
            if clone.returncode != 0:
                err = (clone.stderr or "").strip()[:200]
                self._print(f"[!] Клонирование не удалось: {err}")
                return

        # Шаг 3: патчим setup.py — отключаем проверку CUDA версии
        # (на Kaggle: системная CUDA 12.8, PyTorch собран с CUDA 13.0)
        self._print("[*] Патчу setup.py — пропускаю проверку CUDA version mismatch...")
        setup_py = os.path.join(self.SAGE_SRC, "setup.py")
        with open(setup_py, "r", encoding="utf-8") as f:
            content = f.read()
        # Вставляем monkey-patch после всех import, перед кодом setup.py
        patch = (
            "import torch.utils.cpp_extension\n"
            "# Monkey-patch: отключаем проверку CUDA version mismatch\n"
            "# (системная CUDA 12.8, PyTorch собран с CUDA 13.0)\n"
            "torch.utils.cpp_extension._check_cuda_version = lambda *a, **kw: None\n"
        )
        if "torch.utils.cpp_extension._check_cuda_version" not in content:
            content = content.replace("import torch", patch + "import torch", 1)
            with open(setup_py, "w", encoding="utf-8") as f:
                f.write(content)
            self._print("[*] setup.py пропатчен")

        # Шаг 3b: патчим CUDA-хедер — оборачиваем в #ifdef __CUDACC__
        # (pybind_sm75.cpp включает этот хедер и компилируется g++, который
        #  не знает CUDA intrinsic). Весь CUDA-код → под guard, декларация
        #  C++ функции → снаружи (для взятия адреса &function в pybind).
        hdr = os.path.join(self.SAGE_SRC, "csrc", "qattn", "attn_cuda_sm75.h")
        with open(hdr, "r", encoding="utf-8") as f:
            content = f.read()

        if "#ifdef __CUDACC__" not in content:
            # Извлекаем сигнатуру C++ функции для декларации
            sig = ""
            marker = "torch::Tensor qk_int8_sv_f16_accum_f32_attn_sm75"
            if marker in content:
                cpp_part = content[content.index(marker):]
                sig = cpp_part.split("{", 1)[0] + ";\n"

            guarded = (
                "#ifdef __CUDACC__\n"
                f"{content}\n"
                "#endif  // __CUDACC__\n"
            )
            if sig:
                guarded += f"\n// Декларация для host compiler (pybind берёт &function)\n{sig}"

            with open(hdr, "w", encoding="utf-8") as f:
                f.write(guarded)
            self._print("[*] attn_cuda_sm75.h: весь CUDA-код под #ifdef __CUDACC__")

        # Шаг 4: собираем CUDA-расширение напрямую (без editable wheel)
        self._print("[*] Компилирую CUDA-ядро под sm_75 (это может занять 5-10 мин)...")
        result = subprocess.run(
            [VENV_PYTHON, "setup.py", "build_ext", "--inplace"],
            cwd=self.SAGE_SRC,
            capture_output=True, text=True, timeout=900)

        # Сохраняем полный лог в файл (на случай обрезания в stdout)
        log = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        full = log + "\n" + err
        log_path = os.path.join(self.SAGE_SRC, "build_sm75.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("=== STDOUT ===\n" + log + "\n=== STDERR ===\n" + err)
        self._print(f"[*] Полный лог сохранён в {log_path}")

        # Ищем строки с ошибками компиляции (не Python traceback)
        errors = [l for l in full.split("\n") if "error" in l.lower()]
        # Показываем ТОЛЬКО строки с компиляторными ошибками (C++/CUDA/nvcc/ninja)
        compile_errors = [
            l for l in errors
            if any(x in l.lower() for x in [": error:", "fatal error", "nvcc error",
                                            "c++ error", "cuda error", "cc1plus"])
        ]
        if compile_errors:
            self._print("[!] ОШИБКИ КОМПИЛЯЦИИ:")
            for line in compile_errors[-30:]:
                self._print(f"  ⛔ {line}")
        else:
            # Если нет — показываем последние 20 error-строк
            self._print("[*] Ошибок компиляции не найдено, показываю последние строки:")
            for line in errors[-20:]:
                self._print(f"  ⛔ {line}")
        # и последние 30 строк лога
        self._print("[... последние строки лога ...]")
        for line in full.split("\n")[-30:]:
            self._print(f"  {line}")

        if result.returncode == 0:
            # После build_ext --inplace, .so файлы лежат в csrc/
            # Ставим сам пакет без перекомпиляции
            self._print("[*] CUDA-ядро скомпилировано, устанавливаю пакет...")
            install = subprocess.run(
                [VENV_PYTHON, "-m", "pip", "install", "--no-build-isolation",
                 "--no-deps", "."],
                cwd=self.SAGE_SRC,
                capture_output=True, text=True, timeout=120)
            for line in (install.stdout or "").split("\n")[-10:]:
                self._print(f"  {line}")

            verify = subprocess.run(
                [VENV_PYTHON, "-c", "import sageattention"],
                capture_output=True, text=True, timeout=15)
            if verify.returncode == 0:
                self._print("[OK] SageAttention-SM75 установлен! "
                            "ComfyUI запустится с --use-sage-attention")
                self._set_status("✅ SageAttention-SM75 готов", "#27ae60")
                self.sage_ok = True
                return
            else:
                self._print(f"[!] Пакет установлен, но не импортируется: "
                            f"{verify.stderr.strip()[:200]}")

        self._print(f"[!] Сборка не удалась (код {result.returncode})")
        self._print("[!] Запускаю со split-cross-attention (без Sage)")
        self._set_status("⚠️ SageAttention не установлен — работаю без него",
                         "#f39c12")

    # --- 4. запуск ComfyUI --------------------------------------------
    def _start_comfy(self):
        self._set_status("⏳ Запуск ComfyUI...", "#f39c12")
        attention_flag = ("--use-sage-attention" if getattr(self, "sage_ok", False)
                         else "--use-split-cross-attention")
        self._print(f"[*] Attention: {attention_flag}")
        self.comfy_proc = subprocess.Popen(
            [
                VENV_PYTHON, "main.py",
                "--listen", "0.0.0.0",
                "--port", str(PORT),
                "--enable-cors-header", "*",
                "--disable-auto-launch",
                attention_flag,
                "--preview-method", "auto",
            ],
            cwd=COMFY_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        Thread(target=self._stream, args=(self.comfy_proc, "[COMFY] "),
               daemon=True).start()

    # --- 5. ждём порт --------------------------------------------------
    def _wait_for_port(self):
        self._print("[*] Ожидание запуска сервера...")
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
        self._set_status("✅ ComfyUI запущен, поднимаю туннель...", "#27ae60")

    # --- 6. туннель Cloudflare + парсинг URL ---------------------------
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
            self._print(f"[TUNNEL] {line.rstrip()}")
            m = re.search(r"https://[^\s]+trycloudflare\.com", line)
            if m:
                self.public_url = m.group(0)
                break

        # остаток логов туннеля — в фон
        Thread(target=self._stream, args=(self.tunnel_proc, "[TUNNEL] "),
               daemon=True).start()

        if self.public_url:
            self._show_url(self.public_url)
            self._set_status("✅ ComfyUI доступен!", "#27ae60")
        else:
            self._set_status("⚠️ Туннель поднят, но ссылку найти не удалось — "
                             "проверь лог", "#f39c12")

    # ------------------------------------------------------------------
    # Кнопка-ссылка
    # ------------------------------------------------------------------
    def _show_url(self, url):
        self.url_box.value = (
            f"<a href='{url}' target='_blank' rel='noopener noreferrer' "
            f"style='background:#3498db; color:white; padding:10px 22px; "
            f"text-decoration:none; border-radius:8px; font-size:15px; "
            f"font-weight:bold; display:inline-block; margin-right:12px;'>"
            f"🔗 Открыть ComfyUI</a>"
            f"<div style='font-size:11px; color:#888; margin-top:6px'>{url}</div>"
        )

    # ------------------------------------------------------------------
    # Завершение процессов (общее для «Остановить» и «Перезапустить»)
    # ------------------------------------------------------------------
    def _kill_processes(self):
        for proc in (self.tunnel_proc, self.comfy_proc):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
        # подчищаем хвосты на всякий случай
        for pat in ("main.py", "cloudflared"):
            subprocess.run(["pkill", "-9", "-f", pat], capture_output=True)

    # ------------------------------------------------------------------
    # Кнопка «Остановить»
    # ------------------------------------------------------------------
    def _on_stop_click(self, _btn):
        if self.stopped:
            return
        self.stopped = True            # это же завершит keep-alive цикл ячейки
        self._set_status("⏳ Останавливаю ComfyUI...", "#f39c12")
        self.stop_btn.disabled = True
        self._kill_processes()
        self.url_box.value = "<i style='color:#888'>ComfyUI остановлен.</i>"
        self._set_status("🛑 ComfyUI остановлен. Запусти ячейку заново, чтобы "
                         "поднять снова.", "#e74c3c")
        self._print("[*] ComfyUI и туннель остановлены.")
        self._flush_log_now()

    # ------------------------------------------------------------------
    # Кнопка «Перезапустить» — гасит процессы и поднимает ComfyUI заново
    # (без перезапуска ядра Kaggle и без переустановки)
    # ------------------------------------------------------------------
    def _on_restart_click(self, _btn):
        if self._starting:
            return                      # уже идёт запуск — игнорируем
        self.restart_btn.disabled = True
        self._set_status("🔄 Перезапуск ComfyUI...", "#f39c12")
        self._print("[*] Перезапуск: гашу старые процессы...")
        self._kill_processes()
        # сброс состояния под новый запуск
        self.stopped = False
        self.public_url = None
        self.comfy_proc = None
        self.tunnel_proc = None
        self.url_box.value = (
            "<i style='color:#888'>Публичная ссылка появится здесь...</i>"
        )
        Thread(target=self._startup, daemon=True).start()

    # ------------------------------------------------------------------
    # keep-alive: держит ячейку «выполняющейся», но прокачивает события ядра
    # ------------------------------------------------------------------
    def _make_kernel_pump(self):
        """Функция, прокачивающая одно сообщение ядра — чтобы кнопки-виджеты
        отвечали, пока ячейка занята keep-alive циклом.

        Возвращает None, если включить не удалось (тогда кнопки не сработают,
        но остановить можно через ⏹ Interrupt).
        """
        try:
            import asyncio
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
            # nest_asyncio разрешает run_until_complete внутри уже запущенного
            # event-loop ядра — без него do_one_iteration (корутина в ipykernel 6)
            # не выполнить из тела ячейки.
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
        """Держит ячейку активной, чтобы Kaggle не усыпил сессию (~40 мин
        бездействия = сон и падение). Останавливается кнопкой «Остановить»
        или ⏹ (Interrupt).
        """
        pump = self._make_kernel_pump()
        if pump is None:
            self._print("[!] Обработку кнопок в keep-alive включить не удалось — "
                        "для остановки используй ⏹ (Interrupt).")
        self._print("[*] keep-alive активен — Kaggle не уснёт. Останови кнопкой "
                    "«Остановить» или ⏹ (Interrupt).")
        try:
            while not self.stopped:
                if pump is not None:
                    try:
                        pump()
                    except Exception:
                        time.sleep(0.2)
                time.sleep(0.05)
        except KeyboardInterrupt:
            self._print("[*] Interrupt — останавливаю ComfyUI и туннель...")
            self._on_stop_click(None)
        self._flush_log_now()


def launch():
    """Создаёт лаунчер и запускает. Возвращает панель виджетов."""
    return ComfyLauncher().launch()


# При `%run start.py` запускаемся автоматически.
if __name__ == "__main__":
    launch()
