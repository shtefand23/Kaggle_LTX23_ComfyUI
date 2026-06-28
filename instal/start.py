#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
start.py
=================================================================
ШАГ 3 из 3. Запускает ComfyUI + Cloudflare-туннель и рисует под
ячейкой панель управления.

Этот файл — ТОЛЬКО тонкий вход (проверки + вызовы).
Вся логика — в модулях:
  * kaggle_env.py      — пути, venv, uv
  * launcher.py         — ComfyLauncher (жизненный цикл)
  * logging_ui.py       — UI + троттлинг лога
  * sage_installer.py   — SageAttention-SM75

Поведение (важно для Kaggle):
  * Ячейка РАБОТАЕТ ПОСТОЯННО (keep-alive), пока пользователь сам её не
    остановит. Это держит kernel «активным», иначе Kaggle через ~40 мин
    бездействия усыпляет сессию и она падает.
  * Кнопки под ячейкой: «🔗 Открыть ComfyUI», «🛑 Остановить», «🔄 Перезапустить».
  * Лог с троттлингом (последние N строк, обновление раз в ~0.5с).

Запуск (в блокноте):  %run instal/start.py
=================================================================
"""

import os
import sys

# ----------------------------------------------------------------------
# 1. Настройка окружения
# ----------------------------------------------------------------------
# Общий модуль рядом с этим файлом — единый источник правды.
try:
    _KE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _KE_DIR = "/kaggle/working/instal"
sys.path.insert(0, _KE_DIR)

import kaggle_env as ke

# Настраиваем окружение uv: ставит UV_* env-переменные и добавляет
# /kaggle/working/bin в PATH. Без этого `uv pip install` падал после
# рестарта сессии (uv не находился в PATH).
ke.setup_env()


# ----------------------------------------------------------------------
# 2. Проверки перед запуском
# ----------------------------------------------------------------------
def check_prerequisites():
    """Быстрая проверка: venv и ComfyUI на месте."""
    if not ke.venv_python_ok():
        # Пробуем починить +x / пересоздать venv
        ke.install_python()
        if not ke.venv_python_ok():
            raise RuntimeError(
                "venv не работает даже после install_python(). "
                "Запусти сначала: !python instal/instal_comfyui.py"
            )

    if not os.path.exists(f"{ke.COMFY_DIR}/main.py"):
        raise RuntimeError(
            f"ComfyUI не найден в {ke.COMFY_DIR}. "
            "Запусти сначала: !python instal/instal_comfyui.py"
        )

    print("[OK] Предварительные проверки пройдены — запускаю ComfyUI...")


# ----------------------------------------------------------------------
# 3. Запуск
# ----------------------------------------------------------------------
def launch():
    """Создаёт лаунчер и запускает. Возвращает панель виджетов."""
    os.chdir(ke.HOME_DIR)
    check_prerequisites()

    from launcher import ComfyLauncher
    return ComfyLauncher().launch()


# При `%run start.py` запускаемся автоматически.
if __name__ == "__main__":
    launch()
