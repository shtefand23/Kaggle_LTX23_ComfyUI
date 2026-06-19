# ComfyUI на Kaggle (2× T4) — установочные скрипты

Три скрипта поднимают **ComfyUI** на Kaggle (2× Tesla T4, CUDA-драйвер 580.x)
и выдают публичную ссылку через **Cloudflare-туннель**. Сделано на скорость и
без конфликтов зависимостей: `uv` + venv (Python 3.12) + torch **cu130**.

> Цель проекта — запуск в одну ячейку, идемпотентность (любой шаг можно
> перезапускать) и переживание рестарта сессии Kaggle без переустановки torch.

## Быстрый старт (в блокноте Kaggle)

Включи GPU **T4 ×2** и интернет, затем выполни ячейки по порядку:

```python
# 0. Получить скрипты (или обновить, если уже клонировано)
!git clone https://github.com/THE-ANGEL-AI/instal.git || git -C instal pull

# 1. ComfyUI + Manager (uv, venv, torch cu130)
!python instal/instal_comfyui.py

# 2. Кастомные ноды + симлинки на модели из /kaggle/input
!python instal/instal_castom_node.py

# 3. Запуск + Cloudflare-туннель + панель управления (держит ячейку живой)
%run instal/start.py
```

После шага 3 под ячейкой появятся кнопки: **🔗 Открыть ComfyUI**,
**🛑 Остановить**, **🔄 Перезапустить**. Ячейка работает постоянно
(keep-alive), чтобы Kaggle не усыпил сессию через ~40 мин простоя.

## Архитектура

| Шаг | Файл | Назначение | Запуск |
|-----|------|------------|--------|
| 1 | `instal_comfyui.py` | uv + venv (Python 3.12) + torch cu130 + клон ComfyUI + ComfyUI-Manager | `!python instal/instal_comfyui.py` |
| 2 | `instal_castom_node.py` | кастомные ноды + симлинки на модели из `/kaggle/input` | `!python instal/instal_castom_node.py` |
| 3 | `start.py` | запуск ComfyUI + Cloudflare-туннель + панель управления | `%run instal/start.py` |
| — | `kaggle_env.py` | общий модуль: пути, установка uv, проверка/ремонт venv | импортируется всеми тремя |

Пути жёстко завязаны на `/kaggle/working` (переживает рестарт сессии) и
`/kaggle/input` (датасеты).

## Ключевые технические решения

- **uv вместо pip/virtualenv** — параллельная установка пакетов, torch и
  зависимости ставятся в разы быстрее.
- **Всё состояние uv в `/kaggle/working`** (бинарь uv, базовый CPython, кэш
  колёс, venv) — единственный каталог, переживающий рестарт сессии Kaggle.
  После рестарта файлы остаются, теряется только бит `+x` → чиним `chmod`,
  а не переустанавливаем torch с нуля.
- **torch cu130 (CUDA 13.0)** — оптимален для драйвера Kaggle 580.x; на cu128
  был warning и более медленный путь.
- **Быстрое внимание на T4 = PyTorch SDPA** (`--use-pytorch-cross-attention`).
  `xformers` и `SageAttention` **не ставим** — несовместимы с Turing (sm_75).
- **MultiGPU через официальную ноду ComfyUI-MultiGPU (DisTorch2)** — вместо
  старого хака ComfyBootlegOffload, который конфликтовал и тормозил на 2× T4.
- **Авто-обновление скриптов** — `start.py` при старте делает `git pull
  --ff-only` из этого репозитория, так что правки прилетают на Kaggle сами.

## Настройка под себя

- **Добавить ноду** — словарь `CUSTOM_NODES` в `instal_castom_node.py`
  (`"имя-папки": "git-url"`). Clone/pull и установка requirements — автоматом.
- **Добавить модель** — список `SYMLINKS` в `instal_castom_node.py`
  (кортеж `(источник_в_/kaggle/input, назначение_в_ComfyUI)`).
- **Общий pip-пакет** — `install_common_extras()` в `instal_comfyui.py`.
- **Флаги запуска ComfyUI** — метод `_start_comfy()` в `start.py`.

## Модели

### Flux2 Dev (GGUF)
- `flux2-dev-Q4_0.gguf` — основная модель (diffusion model)
- `mistral_3_small_flux2_fp8.safetensors` — текст-энкодер (CLIP)
- `flux2-vae.safetensors` — VAE

### LTX 2.3 Video (FP8)
- `ltx-2.3-22b-distilled-1.1-fp8mixed.safetensors` — основная модель
- `gemma-3-12b-it-heretic-fp4-comfy.safetensors` — текст-энкодер
- `ltx-2.3_text_projection_bf16.safetensors` — текст-проекция
- `LTX23_video_vae_bf16.safetensors` — видео-VAE
- `LTX23_audio_vae_bf16.safetensors` — аудио-VAE
- `taeltx2_3.safetensors` — VAE
- `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` — апскейлер
- `LTX-2.3-22b-AV-LoRA-talking-head-v1.safetensors` — LoRA (говорящая голова)
- `LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors` — LoRA

## Установленные ноды (по умолчанию)

| Нода | Назначение |
|------|-----------|
| ComfyUI-Crystools | Мониторинг GPU |
| ComfyUI-GGUF | Загрузка GGUF-моделей |
| ComfyUI-Logic | Логические операции |
| comfy-image-saver | Сохранение изображений |
| ComfyUI-MultiGPU | Multi-GPU (DisTorch2) |
| ComfyUI-KJNodes | Утилиты (маски, латенты, пайплайны) |
| ComfyUI_FL-CosyVoice3 | TTS (синтез/клонирование речи) |
| WhatDreamsCost-ComfyUI | LTX 2.3 Director (таймлайн-оркестратор) |
| ComfyUI-Manager | Менеджер нод |

## Для агентов

Гайд по безопасному редактированию скриптов — в `docs/AGENTS.md`
(локальный, не публикуется), история изменений — в `docs/MEMORY.md`.
Главное: идемпотентность, минимальные диффы, не трогать защитные механизмы,
комментарии на русском в стиле «зачем».
