#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
instal_comfyui.py
=================================================================
ШАГ 1 из 3. Устанавливает ComfyUI и ноду ComfyUI-Manager.

Что здесь сделано для СКОРОСТИ и против КОНФЛИКТОВ:
  * venv создаётся через `uv` вместо `virtualenv` — установка пакетов
    в разы быстрее (uv ставит torch и зависимости параллельно).
  * Python 3.12 — стабильные колёса (wheels) для torch cu130, быстрый
    интерпретатор. Берётся управляемый uv-ом CPython (не зависим от
    того, что окажется в образе Kaggle).
  * torch собран под CUDA 13.0 (cu130) — драйвер Kaggle (580.x) его держит,
    и ComfyUI 0.24 включает на нём оптимизированные CUDA-операции (на cu128
    был warning и более медленный путь). Проверено на 2× T4.
  * xformers НЕ ставим: последние сборки xformers не содержат ядер для
    Turing (T4, compute 7.5) и только тормозят.
  * SageAttention (официальный, thu-ml) СОЗНАТЕЛЬНО НЕ ставим — он
    несовместим с Turing (T4, sm_75). Требует Ampere (sm_80+) или новее.
  * SageAttention-SM75-path (github.com/XUANNISSAN/SageAttention-SM75-path) —
    форк с поддержкой Turing через отдельный CUDA kernel
    `sageattn_qk_int8_pv_fp16_cuda_sm75`. Ставится в рантайме из start.py
    (шаг 3b). Если установка не удалась — fallback на split-cross-attention.
  * Внимание на T4: используем --use-sage-attention (start.py).
    SageAttention-SM75: INT8 QK + FP16 PV через CUDA. Если не установлен —
    ComfyUI автоматически падает на стандартный attention (не крашится).
    Если когда-то перейдёшь на sm_80+ GPU — официальный SageAttention
    можно будет добавить отдельным шагом.
  * НЕ ставим tensorflow и старые diffusers/transformers — они тянут
    свои версии CUDA/численных библиотек и конфликтуют. Современные
    версии приедут вместе с requirements кастомных нод (шаг 2).

Запуск (в блокноте):  !python instal/instal_comfyui.py

Скрипт ИДЕМПОТЕНТЕН: каждый шаг сначала проверяет, не сделан ли он уже
(uv установлен? venv цел? torch с CUDA на месте? репозитории склонированы?),
и пропускает лишнюю работу. Можно безопасно перезапускать.

Вся логика путей/uv/venv вынесена в общий модуль kaggle_env.py — единый
источник правды для всех трёх шагов (там же фикс персистентности uv).
=================================================================
"""

import os
import shutil
import subprocess
import sys

# Общий модуль лежит рядом с этим файлом — подключаем по абсолютному пути,
# не завися от текущего каталога (запуск как `!python instal/instal_comfyui.py`).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kaggle_env as ke
from kaggle_env import (
    HOME_DIR, COMFY_DIR, VENV_PYTHON,
    log, warn, step, run, uv_pip_install,
    ensure_uv, ensure_venv, venv_python_ok,
)

# ----------------------------------------------------------------------
# Параметры, специфичные именно для шага 1 (пути/uv/venv — в kaggle_env.py).
# ----------------------------------------------------------------------
# CUDA 13.0: драйвер Kaggle (580.x) его поддерживает, а ComfyUI 0.24 на cu130
# включает оптимизированные CUDA-операции (на cu128 был warning и медленный путь).
# Проверено на 2× T4: оба GPU работают, предупреждение исчезает.
# Если понадобится откат на 12.8 — поставь cu128.
TORCH_INDEX  = "https://download.pytorch.org/whl/cu130"  # CUDA 13.0

COMFYUI_REPO = "https://github.com/Comfy-Org/ComfyUI.git"
MANAGER_REPO = "https://github.com/ltdrdata/ComfyUI-Manager.git"


def torch_cuda_ok():
    """torch уже стоит в venv и видит CUDA? Тогда переустановка не нужна."""
    if not venv_python_ok():
        return False
    try:
        subprocess.run(
            [VENV_PYTHON, "-c", "import torch; assert torch.cuda.is_available()"],
            check=True, capture_output=True, timeout=120)
        return True
    except (subprocess.SubprocessError, OSError):
        return False


# ----------------------------------------------------------------------
# 1. Системные пакеты (ffmpeg для нод с видео/превью).
# ----------------------------------------------------------------------
def install_system_packages():
    step("Системные пакеты (ffmpeg)")
    if shutil.which("ffmpeg"):
        log("ffmpeg уже установлен (пропуск apt)")
        return
    run("apt-get update -qq", check=False)
    run("apt-get install -y -qq ffmpeg", check=False)


# ----------------------------------------------------------------------
# 2. uv + venv (вся логика — в kaggle_env, тут только последовательность).
# ----------------------------------------------------------------------
def setup_uv_venv():
    ensure_uv()
    ensure_venv()


# ----------------------------------------------------------------------
# 3. PyTorch под CUDA 13.0 (главное для скорости генерации).
# ----------------------------------------------------------------------
def install_torch():
    step("PyTorch для CUDA 13.0 (cu130)")
    if torch_cuda_ok():
        log("torch с рабочей CUDA уже установлен (переустановка пропущена)")
    else:
        uv_pip_install(
            "torch", "torchvision", "torchaudio",
            extra_args=["--index-url", TORCH_INDEX],
        )

    # Проверяем, что torch видит CUDA — сразу ловим проблему, не на запуске.
    run([VENV_PYTHON, "-c",
         "import torch; "
         "print('Torch:', torch.__version__); "
         "print('CUDA build:', torch.version.cuda); "
         "print('CUDA available:', torch.cuda.is_available()); "
         "print('GPU count:', torch.cuda.device_count())"],
        check=False)


# ----------------------------------------------------------------------
# 4. ComfyUI: клон + его зависимости.
# ----------------------------------------------------------------------
def install_comfyui():
    step("ComfyUI")
    if not os.path.exists(COMFY_DIR):
        run(["git", "clone", COMFYUI_REPO, COMFY_DIR])
    else:
        run(["git", "-C", COMFY_DIR, "pull"], check=False)

    uv_pip_install("-r", f"{COMFY_DIR}/requirements.txt")
    log("ComfyUI и его зависимости установлены")


# ----------------------------------------------------------------------
# 5. ComfyUI-Manager (менеджер нод — ставится здесь по ТЗ).
# ----------------------------------------------------------------------
def install_manager():
    step("Нода ComfyUI-Manager")
    manager_dir = f"{COMFY_DIR}/custom_nodes/ComfyUI-Manager"
    if not os.path.exists(manager_dir):
        run(["git", "clone", MANAGER_REPO, manager_dir])
    else:
        run(["git", "-C", manager_dir, "pull"], check=False)

    req = f"{manager_dir}/requirements.txt"
    if os.path.exists(req):
        uv_pip_install("-r", req)
    log("ComfyUI-Manager установлен")


# ----------------------------------------------------------------------
# 6. Небольшой набор общих пакетов, полезных большинству нод.
#    (Современные версии, без старых пинов — чтобы не было конфликтов.)
# ----------------------------------------------------------------------
def install_common_extras():
    step("Общие вспомогательные пакеты")
    uv_pip_install(
        "nvidia-ml-py",   # мониторинг GPU (Crystools)
        "einops",
        "omegaconf",
        "timm",
        "mediapy",
        "loguru",
        "imageio[ffmpeg]", "opencv-python", "ffmpeg-python",
    )
    log("Вспомогательные пакеты установлены")


def main():
    step("ШАГ 1: установка ComfyUI и Manager (uv + torch cu130)")
    os.chdir(HOME_DIR)

    install_system_packages()
    setup_uv_venv()
    install_torch()
    install_comfyui()
    install_manager()
    install_common_extras()

    log("ГОТОВО. ComfyUI установлен. Теперь запусти: !python instal/instal_castom_node.py")


if __name__ == "__main__":
    main()
