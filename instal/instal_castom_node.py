#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
instal_castom_node.py
=================================================================
ШАГ 2 из 3. Ставит кастомные ноды и делает символьные ссылки на
модели (как в исходном блокноте, но без конфликтов).

Главное изменение против тормозов на мульти-GPU:
  * Вместо хака ComfyBootlegOffload.py ставится официальная нода
    ComfyUI-MultiGPU (DisTorch2). Старый гист и DisTorch2 оба патчат
    выгрузку слоёв и КОНФЛИКТУЮТ между собой — отсюда долгая генерация
    на двух T4. Оставляем только ComfyUI-MultiGPU.

Список нод и список ссылок на модели вынесены наверх — правь их там,
ты добавляешь модели и ноды вручную.

Запуск (в блокноте):  !python instal/instal_castom_node.py

Перед работой скрипт проверяет, что ШАГ 1 выполнен (есть uv, рабочий venv
и папка ComfyUI/custom_nodes). Если нет — выходит с понятной подсказкой.
Логика путей/uv/venv — в общем модуле kaggle_env.py.
=================================================================
"""

import os
import subprocess
import sys

# Общий модуль рядом с файлом — единый источник правды (пути, uv, venv).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kaggle_env import (
    COMFY_DIR, NODES_DIR, VENV_PYTHON,
    log, warn, step, run,
    install_python,
)

# ----------------------------------------------------------------------
# СПИСОК КАСТОМНЫХ НОД  (name -> git-репозиторий).
# Добавляй/убирай ноды прямо здесь.
# ----------------------------------------------------------------------
CUSTOM_NODES = {
    "ComfyUI-Crystools":  "https://github.com/crystian/ComfyUI-Crystools.git",
    "ComfyUI-GGUF":       "https://github.com/city96/ComfyUI-GGUF.git",
    "ComfyUI-Logic":      "https://github.com/theUpsider/ComfyUI-Logic.git",
    "comfy-image-saver":  "https://github.com/giriss/comfy-image-saver.git",
    # Официальная мульти-GPU нода (DisTorch2). Заменяет ComfyBootlegOffload.py.
    "ComfyUI-MultiGPU":   "https://github.com/pollockjj/ComfyUI-MultiGPU.git",
    # KJNodes — большой набор утилитарных нод (маски, латенты, пайплайны и т.д.).
    "ComfyUI-KJNodes":    "https://github.com/kijai/ComfyUI-KJNodes.git",
    # FL-CosyVoice3 — синтез/клонирование речи (TTS) внутри графа ComfyUI.
    "ComfyUI_FL-CosyVoice3": "https://github.com/filliptm/ComfyUI_FL-CosyVoice3.git",
    # Ltx 2.3 Director
    "WhatDreamsCost-ComfyUI": "https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI.git",
    # LTX2 MultiGPU — авторская нода THE-ANGEL-AI.
    # Собственная разработка с нуля: Hybrid Split Loader для LTX 2.3 GGUF на 2×T4 (Kaggle).
    "ComfyUI-LTX2-MultiGPU": "https://github.com/THE-ANGEL-AI/ComfyUI-LTX2-MultiGPU.git",
}

# ----------------------------------------------------------------------
# СИМВОЛЬНЫЕ ССЫЛКИ НА МОДЕЛИ  (источник в /kaggle/input -> папка ComfyUI).
# Это твой раздел: меняй пути под свои датасеты/модели.
# ----------------------------------------------------------------------
SYMLINKS = [
    # (Flux2)
    ("/kaggle/input/datasets/theangel/flux2-dev32b/flux2-dev-Q4_0.gguf",
     f"{COMFY_DIR}/models/diffusion_models/flux2-dev-Q4_0.gguf"),

    ("/kaggle/input/datasets/theangel/flux2-dev32b/mistral_3_small_flux2_fp8.safetensors",
     f"{COMFY_DIR}/models/text_encoders/mistral_3_small_flux2_fp8.safetensors"),

    ("/kaggle/input/datasets/theangel/flux2-dev32b/flux2-vae.safetensors",
     f"{COMFY_DIR}/models/vae/flux2-vae.safetensors"),

    ("/kaggle/input/datasets/theangel/flux2-dev32b/Flux_2-Turbo-LoRA_comfyui.safetensors",
     f"{COMFY_DIR}/models/loras/Flux_2-Turbo-LoRA_comfyui.safetensors"),

    # (Ltx 2.3 video)
    ("/kaggle/input/models/theangel/ltx-2-3/other/default/4/gemma-3-12b-it-heretic-fp4-comfy.safetensors",
     f"{COMFY_DIR}/models/text_encoders/gemma-3-12b-it-heretic-fp4-comfy.safetensors"),

    ("/kaggle/input/models/theangel/ltx-2-3/other/default/4/ltx-2.3_text_projection_bf16.safetensors",
     f"{COMFY_DIR}/models/text_encoders/ltx-2.3_text_projection_bf16.safetensors"),

    ("/kaggle/input/models/theangel/ltx-2-3/other/default/4/LTX23_audio_vae_bf16.safetensors",
     f"{COMFY_DIR}/models/vae/LTX23_audio_vae_bf16.safetensors"),

    ("/kaggle/input/models/theangel/ltx-2-3/other/default/4/LTX23_video_vae_bf16.safetensors",
     f"{COMFY_DIR}/models/vae/LTX23_video_vae_bf16.safetensors"),

    ("/kaggle/input/models/theangel/ltx-2-3/other/default/4/taeltx2_3.safetensors",
     f"{COMFY_DIR}/models/vae/taeltx2_3.safetensors"),

    ("/kaggle/input/models/theangel/ltx-2-3/other/default/4/ltx-2.3-22b-distilled-1.1-Q6_K.gguf",
     f"{COMFY_DIR}/models/diffusion_models/ltx-2.3-22b-distilled-1.1-Q6_K.gguf"),

    ("/kaggle/input/models/theangel/ltx-2-3/other/default/4/ltx-2.3-22b-distilled-1.1-UD-Q5_K_M.gguf",
     f"{COMFY_DIR}/models/diffusion_models/ltx-2.3-22b-distilled-1.1-UD-Q5_K_M.gguf"),

    ("/kaggle/input/models/theangel/ltx-2-3/other/default/4/ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
     f"{COMFY_DIR}/models/latent_upscale_models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors"),

    ("/kaggle/input/models/theangel/ltx-2-3/other/default/4/LTX-2.3-22b-AV-LoRA-talking-head-v1.safetensors",
     f"{COMFY_DIR}/models/loras/LTX-2.3-22b-AV-LoRA-talking-head-v1.safetensors"),

    ("/kaggle/input/models/theangel/ltx-2-3/other/default/4/LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors",
     f"{COMFY_DIR}/models/loras/LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors"),

    ("/kaggle/input/models/theangel/ltx-2-3/other/default/4/ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors",
     f"{COMFY_DIR}/models/loras/ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors")
]


def uv_pip_install_req(req_path):
    """Ставит requirements ноды в наш venv через uv."""
    result = run(["uv", "pip", "install", "--python", VENV_PYTHON, "-r", req_path], check=False)
    if result and result.returncode != 0:
        warn(f"Установка requirements ноды не удалась: {req_path}")


def check_prerequisites():
    """Проверяем, что ШАГ 1 выполнен: есть uv, рабочий venv и custom_nodes."""
    step("Проверка окружения (результат ШАГА 1)")

    # install_python() централизованно ставит/чинит uv + venv (включая +x).
    install_python()

    if not os.path.exists(NODES_DIR):
        raise RuntimeError(
            f"Не найдена папка {NODES_DIR}. "
            "Сначала запусти: !python instal/instal_comfyui.py"
        )
    log("Окружение готово: uv, venv и ComfyUI на месте")


# ----------------------------------------------------------------------
# Установка одной ноды: clone (или pull) + её requirements.
# ----------------------------------------------------------------------
def install_node(name, repo):
    target = os.path.join(NODES_DIR, name)
    if not os.path.exists(target):
        run(["git", "clone", repo, target])
    else:
        # Если remote URL изменился (форк переехал) — обновляем
        cur = subprocess.run(
            ["git", "-C", target, "remote", "get-url", "origin"],
            capture_output=True, text=True).stdout.strip()
        if cur != repo:
            warn(f"Смена remote URL: {cur} → {repo}")
            run(["git", "-C", target, "remote", "set-url", "origin", repo])
        run(["git", "-C", target, "pull"], check=False)

    req = os.path.join(target, "requirements.txt")
    if os.path.exists(req):
        uv_pip_install_req(req)
    log(f"Нода готова: {name}")


# ----------------------------------------------------------------------
# Создание символьной ссылки на модель (идемпотентно).
# ----------------------------------------------------------------------
def make_symlink(src, dst):
    if not os.path.exists(src):
        warn(f"Источник не найден, пропуск: {src}")
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.islink(dst) or os.path.exists(dst):
        os.remove(dst)            # пересоздаём, чтобы ссылка всегда была актуальной
    os.symlink(src, dst)
    log(f"Ссылка: {os.path.basename(dst)}")


# ----------------------------------------------------------------------
# Авто-вставка SageAttention-T4 в workflow
# ----------------------------------------------------------------------
def inject_sageattn_into_workflows():
    print()
    print('\033[96m=== Авто-вставка SageAttention-T4 в workflow ===\033[0m', flush=True)

    sage_node_dir = os.path.join(NODES_DIR, 'SageAttention-T4')
    if not os.path.isdir(sage_node_dir):
        warn('Нода SageAttention-T4 не найдена в custom_nodes — пропускаю')
        return

    injector = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'scripts', 'inject_sageattn_workflow.py'
    )

    if not os.path.exists(injector):
        warn(f'Инжектор не найден: {injector}')
        log('Добавь ноду SageAttention-T4 вручную или перезапусти скрипт')
        return

    workflows_dir = os.path.join(COMFY_DIR, 'user', 'default', 'workflows')
    if not os.path.isdir(workflows_dir):
        warn(f'Папка workflow не найдена: {workflows_dir}')
        log('Добавь ноду SageAttention-T4 вручную или сохрани workflow и перезапусти скрипт')
        return

    run([sys.executable, injector, workflows_dir], check=False)


def main():
    step("ШАГ 2: кастомные ноды + ссылки на модели")

    check_prerequisites()

    step("Установка кастомных нод")
    for name, repo in CUSTOM_NODES.items():
        install_node(name, repo)

    step("Символьные ссылки на модели")
    for src, dst in SYMLINKS:
        make_symlink(src, dst)

    log("ГОТОВО. Ноды и модели на месте. Теперь запусти: %run instal/start.py")
    # SageAttention-T4 workflow injection happens later in start.py (after symlink creation)


if __name__ == "__main__":
    main()

