# Память проекта — THE-ANGEL-AI ComfyUI

## Обзор
Установочные скрипты для ComfyUI на Kaggle (2× T4, CUDA 580.x).
Четыре файла: `kaggle_env.py` (общий модуль) + `instal_comfyui.py` → `instal_castom_node.py` → `start.py`.

---

## Актуальное состояние

### Git
- Ветка: `main` (переименована из `master`)
- Репо: `github.com/THE-ANGEL-AI/instal.git`
- Коммитов: 2+

### Структура файлов
```
instal/
├─ kaggle_env.py            # ОБЩИЙ МОДУЛЬ: пути, uv, venv, ремонт +x
├─ instal_comfyui.py        # ШАГ 1: uv + venv + torch cu130 + ComfyUI + Manager
├─ instal_castom_node.py    # ШАГ 2: кастомные ноды + симлинки моделей
├─ start.py                 # ШАГ 3: запуск + Cloudflare-туннель + keep-alive
├─ docs/
│  ├─ AGENTS.md             # Инструкция для агентов
│  └─ MEMORY.md             # Этот файл
└─ README.md
```

### Кастомные ноды (`CUSTOM_NODES`)
| Нода | Репозиторий |
|------|------------|
| ComfyUI-Crystools | `github.com/crystian/ComfyUI-Crystools` |
| ComfyUI-GGUF | `github.com/city96/ComfyUI-GGUF` |
| ComfyUI-Logic | `github.com/theUpsider/ComfyUI-Logic` |
| comfy-image-saver | `github.com/giriss/comfy-image-saver` |
| ComfyUI-MultiGPU | `github.com/pollockjj/ComfyUI-MultiGPU` |
| ComfyUI-KJNodes | `github.com/kijai/ComfyUI-KJNodes` |
| ComfyUI_FL-CosyVoice3 | `github.com/filliptm/ComfyUI_FL-CosyVoice3` |
| WhatDreamsCost-ComfyUI | `github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI` |

**Итого: 8 нод**

### Симлинки моделей (`SYMLINKS`)
**Flux2 (3 шт):**
- `flux2-dev-Q4_0.gguf` → `diffusion_models/`
- `mistral_3_small_flux2_fp8.safetensors` → `text_encoders/`
- `flux2-vae.safetensors` → `vae/`

**LTX 2.3 (10 шт):**
- `gemma-3-12b-it-heretic-fp4-comfy.safetensors` → `text_encoders/`
- `ltx-2.3_text_projection_bf16.safetensors` → `text_encoders/`
- `LTX23_audio_vae_bf16.safetensors` → `vae/`
- `LTX23_video_vae_bf16.safetensors` → `vae/`
- `taeltx2_3.safetensors` → `vae/`
- `ltx-2.3-22b-distilled-1.1-fp8mixed.safetensors` → `diffusion_models/`
- `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` → `latent_upscale_models/`
- `LTX-2.3-22b-AV-LoRA-talking-head-v1.safetensors` → `loras/`
- `LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors` → `loras/`

**Итого: 13 симлинков**

### Флаги обновления (`start.py`)
- `AUTO_UPDATE_NODES = True` (git pull нод при старте)
- `AUTO_UPDATE_NODE_REQS = False` (не переустанавливать requirements в venv)

---

## Изменения

### 2026-06-19 — Синхронизация с GitHub
**Сделано:**
- Обновлены `CUSTOM_NODES`: добавлена `WhatDreamsCost-ComfyUI` (LTX 2.3 Director), удалена `ComfyUI-QwenVL`
- Обновлены `SYMLINKS`: добавлено 10 LTX 2.3 моделей (total: 13)
- Проверена актуальность всех файлов с удалённым репозиторием `THE-ANGEL-AI/Kaggle_Workspace`

**Файлы:** `instal_castom_node.py`

---

### 2026-06-19 — Переименование ветки
**Сделано:** `master` → `main`

---

### 2026-06-19 — Первый коммит, README, публикация на GitHub
**Сделано:**
- Создан `README.md` (корень репо, публичный)
- Вынесен общий модуль `kaggle_env.py` (единый источник правды: пути, uv, venv, ремонт +x)
- `instal_castom_node.py`: добавлены ноды ComfyUI-KJNodes и ComfyUI_FL-CosyVoice3
- `start.py`: флаги `AUTO_UPDATE_NODES=True`, `AUTO_UPDATE_NODE_REQS=False`
- Инициализирован git, ветка `master`, первый коммит от THE-ANGEL-AI

---

### 2026-06-17 — Исправление venv после рестарта Kaggle
**Проблема:** После рестарта сессии Kaggle бинарник `uv` терял бит `+x`.

**Решение:**
- `kaggle_env.py`: `ensure_uv()` проверяет существующий бинарник и возвращает `+x`
- `kaggle_env.py`: `repair_venv_perms()` чинит venv, uv, базовый CPython
- `start.py`: делегирует ремонт в `kaggle_env.repair_venv_perms()`

---

### 2026-06-17 — Система обновлений через git
**Добавлено:** `start.py` — метод `_check_git_updates()` автоматически проверяет и скачивает обновления скриптов из GitHub.

**Логика:** git fetch → сравнение с origin → git pull --ff-only.

---

## Решения / паттерны
- **Общий модуль:** `kaggle_env.py` — единый источник правды для путей/uv/venv. Все три скрипта импортируют его.
- **venv на Kaggle:** `uv` ставится standalone-инсталлятором в `/kaggle/working/bin` (персистентный) через `UV_INSTALL_DIR`, НЕ через pip
- **PYTHON_VERSION:** `"3.12"` (управляется uv, берёт стабильную минорную версию)
- **torch:** cu130 (CUDA 13.0) — оптимальный для драйвера Kaggle 580.x
- **xformers/SageAttention:** не ставим — несовместимы с T4 (Turing, sm_75)
- **MultiGPU:** через официальную ноду ComfyUI-MultiGPU (DisTorch2), не через хак ComfyBootlegOffload

---

## Известные проблемы / TODO
_(сюда записываем баги и задачи)_
