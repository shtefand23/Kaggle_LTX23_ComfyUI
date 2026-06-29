#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kaggle_env.py
=================================================================
ОБЩИЙ МОДУЛЬ (единый источник правды) для всех трёх шагов установки
ComfyUI на Kaggle: instal_comfyui.py, instal_castom_node.py, start.py.

Зачем он нужен
--------------
Раньше логика «пути + установка uv + проверка venv + ремонт +x» была
ПРОДУБЛИРОВАНА в трёх файлах с расхождениями. Из-за расхождений ломалось
переживание рестарта сессии Kaggle. Теперь всё в одном месте.

Главная идея надёжности: ВСЁ состояние uv лежит в /kaggle/working —
единственном каталоге, который переживает рестарт сессии Kaggle:

    UV_INSTALL_DIR        (сам бинарь uv)        -> /kaggle/working/bin
    UV_PYTHON_INSTALL_DIR (базовый CPython)      -> /kaggle/working/uv-python
    UV_CACHE_DIR          (колёса, в т.ч. torch) -> /kaggle/working/uv-cache
    venv                                          -> /kaggle/working/venv

После рестарта Kaggle файлы остаются на месте, но теряют бит исполнения
(+x). Поэтому единственный нужный ремонт — вернуть +x (repair_venv_perms),
а НЕ переустанавливать uv/torch с нуля.

КЛЮЧЕВОЙ ФИКС: uv ставится через переменную окружения UV_INSTALL_DIR.
Раньше использовался флаг `--bin-dir`, которого у инсталлятора uv НЕТ —
он молча игнорировался, и uv уезжал в ~/.local/bin (НЕ персистентный),
после рестарта пропадал, и приходилось всё переустанавливать.
=================================================================
"""

import os
import shutil
import subprocess

# ----------------------------------------------------------------------
# Пути и параметры. Меняй здесь — подхватится во всех трёх скриптах.
# ----------------------------------------------------------------------
HOME_DIR      = "/kaggle/working"
VENV_DIR      = f"{HOME_DIR}/venv"
VENV_PYTHON   = f"{VENV_DIR}/bin/python"
COMFY_DIR     = f"{HOME_DIR}/ComfyUI"
NODES_DIR     = f"{COMFY_DIR}/custom_nodes"

# Персистентные каталоги uv (все в /kaggle/working — переживают рестарт).
UV_LOCAL_DIR  = f"{HOME_DIR}/bin"        # сам бинарь uv (UV_INSTALL_DIR)
UV_PYTHON_DIR = f"{HOME_DIR}/uv-python"  # управляемый uv-ом базовый CPython
UV_CACHE_DIR  = f"{HOME_DIR}/uv-cache"   # кэш колёс (torch не качается заново)

PYTHON_VERSION = "3.12"                   # версия интерпретатора в venv

UV_INSTALL_URL = "https://astral.sh/uv/install.sh"


# ----------------------------------------------------------------------
# Единый стиль вывода (раньше дублировался в каждом файле).
# ----------------------------------------------------------------------
def log(msg):   print(f"\n\033[92m✅ {msg}\033[0m", flush=True)
def warn(msg):  print(f"\n\033[93m⚠️  {msg}\033[0m", flush=True)
def step(msg):  print(f"\n\033[96m=== {msg} ===\033[0m", flush=True)


def run(cmd, check=True, **kwargs):
    """Печатает и выполняет команду. По умолчанию падает при ошибке."""
    if isinstance(cmd, str):
        printable = cmd
        kwargs.setdefault("shell", True)
    else:
        printable = " ".join(cmd)
        kwargs.setdefault("shell", False)
    print(f"$ {printable}", flush=True)
    return subprocess.run(cmd, check=check, **kwargs)


# ----------------------------------------------------------------------
# Настройка окружения uv. Лёгкая и безопасная при импорте — вызывается
# автоматически в конце модуля, чтобы любой импортирующий скрипт сразу
# получил правильный PATH и env-переменные uv.
# ----------------------------------------------------------------------
def setup_env():
    """Готовит окружение uv: персистентные каталоги + uv в PATH.

    Без тяжёлой работы (ничего не качает) — можно звать сколько угодно раз.
    """
    # Кэш uv и venv на Kaggle на разных ФС — hardlink не работает, uv ругается.
    # copy-режим убирает предупреждение и лишние попытки слинковать.
    os.environ.setdefault("UV_LINK_MODE", "copy")
    # uv не задаёт интерактивных вопросов (в блокноте отвечать некому).
    os.environ.setdefault("UV_NO_PROMPT", "1")
    # Базовый CPython и кэш — в персистентные каталоги /kaggle/working.
    os.environ.setdefault("UV_PYTHON_INSTALL_DIR", UV_PYTHON_DIR)
    os.environ.setdefault("UV_CACHE_DIR", UV_CACHE_DIR)
    # Брать только управляемый uv-ом python (не системный из ~, который пропадёт).
    os.environ.setdefault("UV_PYTHON_PREFERENCE", "only-managed")

    # Каталоги создаём заранее (терпимо к ошибкам — для локального импорта вне Kaggle).
    for d in (UV_LOCAL_DIR, UV_CACHE_DIR):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass

    # Персистентный каталог с uv — в начало PATH (после рестарта мог выпасть).
    # ИМЕННО этого не хватало в start.py: его `uv pip install` падал после рестарта.
    if os.path.isdir(UV_LOCAL_DIR) and UV_LOCAL_DIR not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = UV_LOCAL_DIR + os.pathsep + os.environ.get("PATH", "")


# ----------------------------------------------------------------------
# Установка uv. Идемпотентна: ставит, только если его нет, и чинит +x.
# ----------------------------------------------------------------------
def ensure_uv():
    """Гарантирует наличие рабочего uv в персистентном каталоге.

    Используем standalone-инсталлятор (curl), а НЕ pip — потому что:
      1) системный Python на Kaggle «externally managed» (PEP 668), pip падает;
      2) pip ставит uv в ~/.local/bin — НЕ персистентный, после рестарта пропадёт.

    Инсталлятор кладёт бинарь в UV_INSTALL_DIR=/kaggle/working/bin (персистентный).
    """
    setup_env()

    # Уже в PATH и работает — выходим.
    if shutil.which("uv"):
        log("uv уже установлен (пропуск)")
        return

    # Бинарь есть на диске, но потерял +x после рестарта Kaggle — чиним дёшево.
    uv_bin = os.path.join(UV_LOCAL_DIR, "uv")
    if os.path.exists(uv_bin):
        warn("uv найден, но без бита +x (рестарт Kaggle снял) — возвращаю +x")
        try:
            os.chmod(uv_bin, 0o755)
        except OSError:
            pass
        os.environ["PATH"] = UV_LOCAL_DIR + os.pathsep + os.environ.get("PATH", "")
        if shutil.which("uv"):
            log("uv починен возвратом +x")
            return

    step("Установка uv (standalone → /kaggle/working/bin)")
    os.makedirs(UV_LOCAL_DIR, exist_ok=True)
    installer = os.path.join(UV_LOCAL_DIR, "uv-install.sh")
    run(["curl", "-LsSf", UV_INSTALL_URL, "-o", installer])
    # КЛЮЧЕВОЙ ФИКС: каталог задаётся переменной UV_INSTALL_DIR, а НЕ флагом
    # --bin-dir (которого у инсталлятора нет). UV_NO_MODIFY_PATH=1 — не трогать
    # профили шелла (нам это не нужно, PATH правим сами через setup_env).
    env = dict(os.environ)
    env["UV_INSTALL_DIR"] = UV_LOCAL_DIR
    env["UV_NO_MODIFY_PATH"] = "1"
    run(["sh", installer], env=env)

    os.environ["PATH"] = UV_LOCAL_DIR + os.pathsep + os.environ.get("PATH", "")
    if not shutil.which("uv"):
        raise RuntimeError("Не удалось установить uv — проверь лог выше")
    log("uv установлен в персистентный каталог /kaggle/working/bin")


# ----------------------------------------------------------------------
# Проверка и ремонт venv.
# ----------------------------------------------------------------------
def venv_python_ok():
    """venv считается рабочим, только если его python РЕАЛЬНО запускается.

    /kaggle/working/venv переживает рестарт сессии, а вот бит +x на
    интерпретаторе и базовом CPython слетает → симлинк цел, но не исполняется.
    Поэтому проверяем именно запуском, а не os.path.exists.
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
        # Ловим stderr, если бинарь есть, но падает (libc, kernel, ...)
        try:
            err = subprocess.run(
                [VENV_PYTHON, "-c", "pass"],
                capture_output=True, timeout=15
            )
            detail = (err.stderr or b"").decode("utf-8", errors="replace")[:500]
        except Exception as e2:
            detail = str(e2)[:500]
        warn(f"venv python есть, но НЕ запускается: {detail}")
        return False


def diagnose_venv():
    """Подробно объясняет, ПОЧЕМУ venv не запускается (для лога после рестарта)."""
    p = VENV_PYTHON
    if not os.path.lexists(p):
        return "venv/bin/python ОТСУТСТВУЕТ (папка venv не создана или удалена)"
    if os.path.islink(p):
        target = os.path.realpath(p)
        if not os.path.exists(target):
            return (f"venv/bin/python — БИТЫЙ СИМЛИНК на {os.readlink(p)} "
                    f"(базовый CPython не пережил рестарт сессии)")
        if not os.access(target, os.X_OK):
            return (f"базовый CPython есть ({target}), но БЕЗ бита +x "
                    f"(рестарт Kaggle снял право исполнения)")
    elif not os.access(p, os.X_OK):
        return "venv/bin/python есть, но БЕЗ бита +x (рестарт снял исполнение)"
    return "python на месте и исполняем, но падает при запуске (см. ошибку ниже)"


def repair_venv_perms():
    """Дёшево чинит самую частую поломку после рестарта: слетевший бит +x.

    Возвращает True, если после ремонта venv заработал. Не пересоздаёт venv и
    не трогает torch — экономит минуты на каждом старте.
    """
    candidates = []
    if os.path.lexists(VENV_PYTHON):
        candidates.append(VENV_PYTHON)
        real = os.path.realpath(VENV_PYTHON)
        if real != VENV_PYTHON:
            candidates.append(real)
    # Бинарь uv в персистентном каталоге — тоже теряет +x после рестарта.
    uv_bin = os.path.join(UV_LOCAL_DIR, "uv")
    if os.path.exists(uv_bin):
        candidates.append(uv_bin)
    # Все исполняемые python в персистентном каталоге uv-CPython.
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
        warn("Вернул бит +x интерпретатору venv/uv-python (после рестарта слетал)")
    return venv_python_ok()


def repair_base_python_via_uv():
    """Если базовый CPython битый (libc/kernel), удаляет старый и ставит свежий.

    ВАЖНО: эта функция НЕ чинит venv — старый venv ссылается на старый
    бинарник (другой путь). Она только готовит РАБОЧИЙ базовый CPython,
    чтобы следующий `uv venv --clear` создал venv с новым CPython.
    Пакеты переставятся из uv-кэша (быстро, torch уже скачан).

    Возвращает:
      True  — базовый CPython переустановлен, можно создавать venv заново;
      False — uv не смог установить CPython (надо переустановить uv).
    """
    # 1. Удаляем старый CPython — uv поймёт, что надо ставить свежий
    #    (без этого uv говорит "already installed" и пропускает установку).
    if os.path.isdir(UV_PYTHON_DIR):
        warn(f"Удаляю старый базовый CPython: {UV_PYTHON_DIR}")
        shutil.rmtree(UV_PYTHON_DIR, ignore_errors=True)

    # 2. Убеждаемся, что uv в PATH (после restart мог пропасть).
    ensure_uv()

    # 3. Ставим свежий CPython для текущего ядра Kaggle.
    warn("Устанавливаю свежий базовый CPython через uv python install...")
    result = run(["uv", "python", "install", PYTHON_VERSION], check=False)
    if result.returncode != 0:
        warn(f"uv python install не удался (код {result.returncode}) — "
             f"нужна полная переустановка")
        return False

    # 4. Проверяем, что свежий python работает (на всякий случай).
    #    Ищем любой python3.12 в UV_PYTHON_DIR (uv мог установить новый).
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
        warn(f"Свежий CPython работает: {fresh_python}. "
             f"Теперь нужен новый venv (будет создан автоматически).")
        return True

    warn("Не удалось найти работающий CPython после uv python install")
    return False


def ensure_venv():
    """Гарантирует рабочий venv. Идемпотентно и максимально дёшево.

    Логика по возрастанию стоимости:
      1) venv уже рабочий                          -> ничего не делаем;
      2) папка есть, но битый -> ремонт +x          -> torch не трогаем;
      3) +x не помог -> переустановка CPython через uv
         (подготовка к пересозданию venv, пакеты из uv-кэша);
      4) всё плохо / venv нет -> пересоздаём venv   -> uv venv (+seed).

    Returns:
      True  — venv уже работал (ничего не делали);
      False — venv был починен/пересоздан (torch и пакеты могли пропасть).
    """
    step("Проверка/создание venv")
    if venv_python_ok():
        log(f"venv уже существует и рабочий: {VENV_DIR} (пересоздание пропущено)")
        return True

    if os.path.exists(VENV_DIR):
        warn(f"venv найден, но нерабочий. Причина: {diagnose_venv()}")
        # Этап 2: дёшево чиним +x (частая поломка после рестарта Kaggle).
        if repair_venv_perms():
            log(f"venv починен возвратом +x — пересоздание и переустановка "
                f"torch НЕ нужны: {VENV_DIR}")
            return False
        # Этап 3: +x не помог — возможно, обновилось ядро Kaggle и старый
        # CPython несовместим с libc. Удаляем его и ставим свежий.
        warn(f"+x не помог — пробую переустановить базовый CPython: {VENV_DIR}")
        repair_base_python_via_uv()
        # NB: repair_base_python_via_uv НЕ чинит venv (старый symlink
        # указывает на удалённый CPython). Он только готовит свежий CPython
        # для следующего шага. Продолжаем с пересозданием venv.

    ensure_uv()  # для пересоздания нужен uv
    # --seed кладёт pip/setuptools внутрь venv — некоторым нодам это нужно.
    # --clear молча перезаписывает существующую папку (без вопроса «очистить?»).
    run(["uv", "venv", VENV_DIR, "--python", PYTHON_VERSION, "--seed", "--clear"])
    if not venv_python_ok():
        raise RuntimeError("venv создан, но python не запускается — смотри лог выше")
    log(f"venv создан на Python {PYTHON_VERSION}: {VENV_DIR}")
    return False


def torch_cuda_ok():
    """Проверяет, что torch установлен в venv и видит CUDA.

    Используется после пересоздания venv или после прерванной установки,
    чтобы не пропустить переустановку, если torch битый/отсутствует.
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
    """Гарантирует рабочий Python: uv в PATH + venv (создан/починен/пересоздан).

    Единая точка входа для всех трёх скриптов (instal_comfyui.py,
    instal_castom_node.py, start.py). Внутри вызывает:
       1. ensure_uv()   — ставит uv-бинарь (если нет / битый),
       2. ensure_venv() — проверяет venv, чинит +x, переустанавливает
                          CPython, при необходимости пересоздаёт venv.

    Идемпотентна и максимально дёшева: если всё уже работает — ничего не делает.

    Returns:
      True  — все компоненты уже работали (ничего не делали);
      False — были выполнены ремонт/пересоздание (пакеты могли пропасть).
    """
    ensure_uv()
    return ensure_venv()


def uv_pip_install(*packages, extra_args=None):
    """uv pip install в наш venv (быстрее обычного pip)."""
    cmd = ["uv", "pip", "install", "--python", VENV_PYTHON]
    if extra_args:
        cmd += list(extra_args)
    cmd += list(packages)
    run(cmd)


# Настраиваем окружение сразу при импорте — любой скрипт, импортировавший
# модуль, получает корректный PATH и env-переменные uv без лишних вызовов.
setup_env()
