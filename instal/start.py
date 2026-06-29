#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
start.py
================================================================
ЕДИНСТВЕННАЯ ТОЧКА ВХОДА для запуска ComfyUI на Kaggle.

Всё в одном: %run instal/start.py
  * сам проверяет, чего не хватает
  * сам доустанавливает ComfyUI / torch / кастомные ноды / модели
  * сам запускает ComfyUI + Cloudflare-туннель + SageAttention + keep-alive

Никаких ручных шагов. Одна ячейка — полный пайплайн.

Архитектура (все модули в instal/):
  * start.py           — тонкий вход (только setup_env + передача лаунчеру)
  * kaggle_env.py      — пути, venv, uv (единый источник правды)
  * launcher.py        — ComfyLauncher (проверки, доустановка, жизненный цикл)
  * logging_ui.py      — LogManager (UI + троттлинг лога)
  * sage_installer.py  — SageAttention-SM75 (Turing T4)
================================================================
"""

import importlib
import os
import shutil
import subprocess
import sys

# ----------------------------------------------------------------------
# 0. Определяем корень instal/
# ----------------------------------------------------------------------
try:
    _KE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _KE_DIR = "/kaggle/working/instal"
sys.path.insert(0, _KE_DIR)

# ----------------------------------------------------------------------
# 1. git pull — обновляем код из репозитория
#    Выполняется ДО очистки кэша, чтобы свежие файлы уже были на диске.
# ----------------------------------------------------------------------
try:
    _r = subprocess.run(
        ["git", "-C", _KE_DIR, "pull", "--ff-only"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if _r.returncode == 0:
        _out = (_r.stdout + _r.stderr).strip()
        if "Already up to date" not in _out and "Already up-to-date" not in _out:
            print("⚙️ [start] git pull: код обновлён из репозитория")
    else:
        print(f"⚙️ [start] git pull: {_r.stderr.strip()[:120]}")
except Exception as _exc:
    print(f"⚙️ [start] git pull не удался: {_exc}")

# ----------------------------------------------------------------------
# 2. Сброс stale-кэша модулей и .pyc
#    После git pull на диске свежие файлы. Вычищаем всё, что могло
#    закэшироваться в памяти (sys.modules) и на диске (__pycache__).
# ----------------------------------------------------------------------

# 2a. Удаляем instal-модули из памяти — Python перечитает свежие .py.
for _mod_name in list(sys.modules.keys()):
    if _mod_name in (
        "kaggle_env", "logging_ui", "launcher", "sage_installer",
        "instal_comfyui", "instal_castom_node",
    ):
        del sys.modules[_mod_name]

# 2b. Чистим все __pycache__ рекурсивно — stale .pyc переживает git pull,
#     и Python может не перекомпилировать, если timestamp совпал.
for _root, _dirs, _files in os.walk(_KE_DIR):
    if "__pycache__" in _dirs:
        shutil.rmtree(os.path.join(_root, "__pycache__"), ignore_errors=True)
        _dirs.remove("__pycache__")

# 2c. Инвалидируем кэш importlib finder'ов — чтобы они перечитали файлы
#     с диска, а не вернули stale spec из внутреннего кэша.
importlib.invalidate_caches()

import kaggle_env as ke

# Ставим UV_* env-переменные и добавляем /kaggle/working/bin в PATH.
# Без этого `uv pip install` падает после рестарта сессии Kaggle.
ke.setup_env()


# ----------------------------------------------------------------------
# 2. Запуск — вся тяжёлая работа в launcher.py
# ----------------------------------------------------------------------
def launch():
    """Передаёт управление ComfyLauncher'у. Тот сам доустановит всё
    необходимое (ComfyUI, torch, ноды) и запустит сервис."""
    os.chdir(ke.HOME_DIR)

    from launcher import ComfyLauncher
    return ComfyLauncher().launch()


# При `%run start.py` запускаемся автоматически.
if __name__ == "__main__":
    launch()
