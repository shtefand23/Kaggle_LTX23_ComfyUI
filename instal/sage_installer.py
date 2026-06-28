#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sage_installer.py
=================================================================
Установка SageAttention-SM75-path (Turing T4, sm_75) + инжект
ноды SageAttentionT4_Apply в workflow.

Вынесен из start.py, чтобы start.py оставался тонким.

Использует LogManager (logging_ui.py) для вывода — логи попадают
в красивую обвязку start.py.

Форк: https://github.com/THE-ANGEL-AI/SageAttention-SM75-path.git
Поддержка Turing (sm_75) через CUDA-ядро sageattn_qk_int8_pv_fp16_cuda_sm75.
=================================================================
"""

import os
import subprocess
import sys

# Путь к репозиторию SageAttention (относительно HOME_DIR)
SAGE_SRC_DIR = "sageattention-sm75"

# Форк с поддержкой Turing (sm_75)
SAGE_REPO = "https://github.com/THE-ANGEL-AI/SageAttention-SM75-path.git"


def _run(cmd, **kwargs):
    """Печатает и выполняет команду, возвращает результат."""
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("timeout", 120)
    print(f"  $ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    return subprocess.run(cmd, **kwargs)


def install(home_dir, venv_python, comfy_dir, logger):
    """Собирает SageAttention-SM75 в venv и линкует custom_node.

    Параметры:
      home_dir     — /kaggle/working
      venv_python  — путь к python в venv
      comfy_dir    — путь к ComfyUI (для custom_nodes symlink)
      logger       — экземпляр LogManager (из logging_ui.py)

    Возвращает:
      True, если SageAttention установлен и готов к использованию.
    """
    logger.set_status("⚙️ Проверяю SageAttention-SM75 (Turing)...", "#f39c12")
    sage_ok = False
    sage_src = os.path.join(home_dir, SAGE_SRC_DIR)

    # --- Шаг 0: уже установлен? ---
    logger.print("[*] Проверяю SageAttention-SM75 (Turing)...")
    check = subprocess.run(
        [venv_python, "-c", "import sageattention"],
        capture_output=True, text=True, timeout=15)
    if check.returncode == 0:
        logger.print("[*] SageAttention уже установлен (пропуск)")
        return True

    # --- Шаг 1: build-зависимости ---
    logger.set_status("⚙️ Устанавливаю SageAttention-SM75...", "#f39c12")
    logger.print("[*] Обновляю setuptools + wheel...")
    subprocess.run(
        [venv_python, "-m", "pip", "install", "--upgrade",
         "setuptools", "wheel"],
        capture_output=True, text=True, timeout=120)

    # --- Шаг 2: клонируем/обновляем репозиторий ---
    if os.path.isdir(sage_src):
        _ensure_fork_remote(sage_src, logger)
        _update_repo(sage_src, logger)
    else:
        _clone_repo(sage_src, logger)

    if not os.path.isdir(sage_src):
        logger.print("[!] Репозиторий SageAttention не доступен — пропуск")
        return False

    # --- Шаг 3: сборка CUDA-расширения ---
    logger.print("[*] Компилирую CUDA-ядро под sm_75 (это может занять 5-10 мин)...")
    result = subprocess.run(
        [venv_python, "setup.py", "build_ext", "--inplace"],
        cwd=sage_src,
        capture_output=True, text=True, timeout=900)

    # Сохраняем полный лог сборки
    _save_build_log(sage_src, result, logger)

    # --- Шаг 4: анализ результата сборки ---
    if result.returncode != 0:
        _log_build_failure(result, logger)
        return False

    # --- Шаг 5: установка пакета ---
    sage_ok = _install_package(sage_src, venv_python, logger)
    if not sage_ok:
        logger.print("[!] Fallback: split-cross-attention (без SageAttention)")
        return False

    # --- Шаг 6: симлинк в custom_nodes ---
    _link_custom_node(sage_src, comfy_dir, logger)

    logger.print("[OK] SageAttention-SM75 готов!")
    return True


def _ensure_fork_remote(sage_src, logger):
    """Переключаем remote origin на форк (если раньше клонировали XUANNISSAN)."""
    subprocess.run(
        ["git", "-C", sage_src, "remote", "set-url", "origin", SAGE_REPO],
        capture_output=True, text=True, timeout=30)
    logger.print("[*] Репозиторий уже склонирован — проверяю обновления форка...")


def _update_repo(sage_src, logger):
    """Сбрасывает локальные патчи и делает pull."""
    subprocess.run(
        ["git", "-C", sage_src, "reset", "--hard", "--quiet"],
        capture_output=True, text=True, timeout=30)
    subprocess.run(
        ["git", "-C", sage_src, "fetch", "--quiet"],
        capture_output=True, text=True, timeout=30)
    pull = subprocess.run(
        ["git", "-C", sage_src, "pull", "--ff-only"],
        capture_output=True, text=True, timeout=60)
    if pull.returncode == 0:
        out = (pull.stdout or "").strip()
        if out and "Already up to date" not in out:
            logger.print(f"[*] Форк обновлён: {out.splitlines()[-3:][0]}")
        else:
            logger.print("[*] Форк актуален")
    else:
        err = (pull.stderr or "").strip()[:200]
        logger.print(f"[!] git pull не удался: {err} (старая версия)")


def _clone_repo(sage_src, logger):
    """Клонирует форк SageAttention."""
    logger.print("[*] Клонирую SageAttention-SM75-path (форк)...")
    clone = subprocess.run(
        ["git", "clone", SAGE_REPO, sage_src],
        capture_output=True, text=True, timeout=120)
    if clone.returncode != 0:
        err = (clone.stderr or "").strip()[:200]
        logger.print(f"[!] Клонирование не удалось: {err}")


def _save_build_log(sage_src, result, logger):
    """Сохраняет лог сборки в файл."""
    log_text = (result.stdout or "").strip()
    err_text = (result.stderr or "").strip()
    log_path = os.path.join(sage_src, "build_sm75.log")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("=== STDOUT ===\n" + log_text + "\n=== STDERR ===\n" + err_text)
        logger.print(f"[*] Полный лог сохранён в {log_path}")
    except OSError:
        pass

    # Парсим ошибки компиляции
    full = log_text + "\n" + err_text
    lines = full.split("\n")
    traceback_start = -1
    for i, l in enumerate(lines):
        if 'File "/kaggle/' in l and 'python' in l.lower():
            traceback_start = i
            break

    if traceback_start > 0:
        compile_lines = lines[:traceback_start]
        logger.print(f"[*] Строк до трейсбека: {len(compile_lines)}")
        err_lines = [
            l for l in compile_lines
            if any(x in l.lower() for x in [
                "error:", "fatal", "undefined", "no member", "not declared",
                "implicit", "failed:", "ninja: build stopped",
                "cannot find", "no such file",
            ])
        ]
        if err_lines:
            logger.print("[!] ОШИБКИ КОМПИЛЯЦИИ/СБОРКИ:")
            for line in err_lines[-40:]:
                logger.print(f"  ⛔ {line}")
            return True  # ошибки найдены
        logger.print("[*] Последние строки компиляции (до трейсбека):")
        for line in compile_lines[-50:]:
            logger.print(f"  {line}")
    else:
        logger.print("[*] Трейсбек не найден, последние строки лога:")
        for line in lines[-30:]:
            logger.print(f"  {line}")
    return False


def _log_build_failure(result, logger):
    """Выводит информацию об ошибке сборки."""
    logger.print(f"[!] Build failed (code {result.returncode})")
    logger.print("[!] Falling back to split-cross-attention (без Sage)")
    logger.set_status("⚠️ SageAttention не установлен — работа без ускорения", "#f39c12")


def _install_package(sage_src, venv_python, logger):
    """Устанавливает собранный пакет в venv."""
    logger.print("[*] CUDA kernel compiled, устанавливаю пакет...")
    install = subprocess.run(
        [venv_python, "-m", "pip", "install", "--no-build-isolation",
         "--no-deps", "."],
        cwd=sage_src,
        capture_output=True, text=True, timeout=120)
    for line in (install.stdout or "").split("\n")[-10:]:
        logger.print(f"  {line}")

    verify = subprocess.run(
        [venv_python, "-c", "import sageattention"],
        capture_output=True, text=True, timeout=15)
    if verify.returncode == 0:
        logger.print("[OK] SageAttention-SM75 installed!")
        return True

    logger.print(f"[!] Пакет установлен, но не импортируется: "
                 f"{verify.stderr.strip()[:200]}")
    return False


def _link_custom_node(sage_src, comfy_dir, logger):
    """Создаёт симлинк SageAttention-T4 в custom_nodes."""
    sage_node_dir = os.path.join(comfy_dir, "custom_nodes", "SageAttention-T4")
    try:
        if os.path.islink(sage_node_dir):
            if os.readlink(sage_node_dir) != sage_src:
                os.unlink(sage_node_dir)
                os.symlink(sage_src, sage_node_dir)
                logger.print("[*] ComfyUI node symlink обновлён: SageAttention-T4")
            else:
                logger.print("[*] ComfyUI node уже в custom_nodes: SageAttention-T4")
        elif not os.path.exists(sage_node_dir):
            os.symlink(sage_src, sage_node_dir)
            logger.print("[*] ComfyUI node симлинк создан: SageAttention-T4")
        else:
            logger.print(f"[*] ComfyUI node dir существует: {sage_node_dir}")
    except OSError as e:
        logger.print(f"[!] Symlink не удался ({e}) — нода не будет обнаружена")


def inject_into_workflows(comfy_dir, logger):
    """Инжектит SageAttentionT4_Apply в workflow JSON.

    Вызывает scripts/inject_sageattn_workflow.py для всех .json
    в ComfyUI/user/default/workflows/.
    """
    # Путь к инжектору — рядом в scripts/
    injector = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "scripts", "inject_sageattn_workflow.py"
    )
    if not os.path.exists(injector):
        logger.print(f"[!] Инжектор не найден: {injector}")
        return

    workflows_dir = os.path.join(comfy_dir, "user", "default", "workflows")
    if not os.path.isdir(workflows_dir):
        logger.print(f"[!] Папка workflow не найдена: {workflows_dir}")
        logger.print("[*] Инжект SageAttention пропущен — сохрани workflow и перезапусти")
        return

    logger.print("[*] Инжект SageAttention-T4 в workflow...")
    subprocess.run(
        [sys.executable, injector, workflows_dir],
        check=False)
    logger.print("[*] Инжект завершён")
