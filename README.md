# ☁️ Kaggle Cloud — ComfyUI (Flux2 + LTX 2.3) на бесплатных 2× Tesla T4

> Проект **[THE ANGEL AI](https://vk.com/theangel_lab)** — запускаем тяжёлые
> генеративные пайплайны **ComfyUI** (Flux2 GGUF, LTX 2.3 Video, TTS) прямо в
> бесплатном Kaggle-блокноте на **двух Tesla T4**, без локального GPU и без
> оплаты облака.

[![Поддержать проект](https://img.shields.io/badge/💖_Поддержать-Boosty-f15f2c?style=for-the-badge)](https://boosty.to/the_angel/donate)
[![ВКонтакте](https://img.shields.io/badge/Сообщество-ВКонтакте-0077FF?style=for-the-badge&logo=vk)](https://vk.com/theangel_lab)

---

## 🎯 Что это за проект

Kaggle бесплатно даёт **2× Tesla T4 (по 16 ГБ) на 30 часов в неделю** — этого
достаточно, чтобы крутить актуальные модели (Flux2, видео-пайплайны, TTS) без
своей видеокарты. Но «голый» Kaggle для ComfyUI — это боль: окружение слетает
после каждого рестарта сессии, мульти-GPU конфликтует, зависимости ломаются.

**Этот репозиторий превращает запуск в одну строку.** Вся логика вынесена в
**идемпотентные Python-скрипты** внутри папки `instal/`. Запускаешь — и через
пару минут получаешь публичную ссылку на работающий ComfyUI.

Ключевая фишка: **самовосстановление окружения**. Kaggle при перезапуске сессии
ломает venv (битый симлинк / слетевший бит `+x`) — скрипты это ловят и **чинят
автоматически за секунды**, не пересобирая всё с нуля.

## 📂 Структура репозитория

```
Kaggle_Workspace_FreeGPU/
├─ .gitignore
├─ README.md                  # этот файл
└─ instal/                    # все установочные скрипты
   ├─ instal_comfyui.py          # ШАГ 1: окружение + ComfyUI + Manager
   ├─ instal_castom_node.py      # ШАГ 2: кастомные ноды + модели
   ├─ start.py                   # ШАГ 3: запуск + туннель + кнопки
   └─ kaggle_env.py              # общий модуль: пути, uv, ремонт venv
```

## 🚀 Быстрый старт (в блокноте Kaggle)

Включи GPU **T4 ×2** и интернет, затем выполни ячейки по порядку:

```python
# 0. Получить скрипты из репозитория (или обновить, если уже клонировано)
!git clone https://github.com/THE-ANGEL-AI/Kaggle_Workspace_FreeGPU.git || \
 git -C Kaggle_Workspace_FreeGPU pull

# 1. ComfyUI + Manager (uv, venv, torch cu130)
!python Kaggle_Workspace_FreeGPU/instal/instal_comfyui.py

# 2. Кастомные ноды + симлинки на модели из /kaggle/input
!python Kaggle_Workspace_FreeGPU/instal/instal_castom_node.py

# 3. Запуск + Cloudflare-туннель + панель управления (держит ячейку живой)
%run Kaggle_Workspace_FreeGPU/instal/start.py
```

> 💡 **Можно одной строкой.** `start.py` сам проверяет всё окружение: если venv,
> ComfyUI или какой-то кастомной ноды нет — он вызовет нужный установщик
> автоматически. Так что для холодного старта достаточно `%run .../instal/start.py`.

После шага 3 под ячейкой появятся кнопки:
- **🔗 Открыть ComfyUI** — публичная ссылка Cloudflare (новая на каждый запуск);
- **🛑 Остановить ComfyUI** — гасит процесс и туннель **без перезапуска ядра**;
- **🔄 Перезапустить** — поднимает ComfyUI заново (новый URL) без переустановки.

Ячейка работает постоянно (keep-alive) — Kaggle не усыпляет сессию через ~40
минут бездействия.

## 🏗️ Архитектура

| Шаг | Файл | Назначение | Запуск |
|-----|------|------------|--------|
| 1 | `instal_comfyui.py` | uv + venv (Python 3.12) + torch cu130 + клон ComfyUI + ComfyUI-Manager | `!python instal/instal_comfyui.py` |
| 2 | `instal_castom_node.py` | кастомные ноды + симлинки на модели из `/kaggle/input` | `!python instal/instal_castom_node.py` |
| 3 | `start.py` | запуск ComfyUI + Cloudflare-туннель + панель управления | `%run instal/start.py` |
| — | `kaggle_env.py` | общий модуль: пути, установка uv, проверка/ремонт venv | импортируется всеми тремя |

Пути жёстко завязаны на `/kaggle/working` (переживает рестарт сессии) и
`/kaggle/input` (датасеты).

## 🛡️ Самовосстановление окружения (главное)

Папка `/kaggle/working` переживает рестарт сессии, но:
1. управляемый `uv`-ом CPython, на который ссылается `venv/bin/python`, лежал в
   кэше `~` и **не** переживает рестарт → битый симлинк;
2. с восстановленных файлов **снимается бит исполнения `+x`** → python физически
   на месте, но не запускается (`Permission denied`).

Раньше любая из этих причин приводила к полной переустановке torch при каждом
старте. Теперь вся логика вынесена в общий модуль **`kaggle_env.py`**:

- всё состояние uv держится в персистентном `/kaggle/working`
  (`UV_INSTALL_DIR` для бинаря, `UV_PYTHON_INSTALL_DIR` для базового CPython,
  `UV_CACHE_DIR` для колёс, сам venv);
- при поломке скрипты сначала пробуют **быстрый `+x`-ремонт за секунды**
  (`repair_venv_perms()`), и только если он не помог — пересоздают venv;
- venv проверяется **реальным запуском** (`python -c pass`), а не наличием файла;
- в лог пишется **точная причина** поломки (битый симлинк / нет `+x` / отсутствует).

Эта логика работает в любом из трёх шагов — окружение чинится автоматически
независимо от того, какую ячейку запустили.

## ⚡ Что оптимизировано для скорости на T4

- **uv вместо pip/virtualenv** — параллельная установка пакетов, torch и
  зависимости ставятся в разы быстрее.
- **torch cu130 (CUDA 13.0)** — оптимален для драйвера Kaggle 580.x; на cu128
  был warning и более медленный путь. Откат: `TORCH_INDEX` в `instal_comfyui.py`.
- **Без xformers и SageAttention** — несовместимы с Turing (T4, sm_75). Быстрое
  внимание даёт нативный **PyTorch SDPA** (`--use-pytorch-cross-attention`).
  SageAttention проверен на железе: требует Ampere (sm_80+).
- **ComfyUI-MultiGPU (DisTorch2)** вместо старого хака `ComfyBootlegOffload.py`
  — гист и DisTorch2 конфликтовали и тормозили генерацию на двух картах.
- **Без tensorflow и старых пинов** `diffusers`/`transformers` — они ломали
  современные ноды.
- **smart-memory включён** — модель кэшируется в VRAM между генерациями.

## 🖥️ Мульти-GPU (2× T4)

В графе используй ноды **ComfyUI-MultiGPU** (DisTorch2):
`UnetLoaderGGUFAdvancedDisTorch2MultiGPU` для Flux2-GGUF и
`*CLIPLoaderGGUFDisTorch2MultiGPU` для текст-энкодера — они распределяют слои
между `cuda:0`, `cuda:1` и CPU. Для двух T4 удобно начать с режима Virtual VRAM
или ratio (например, 0.6/0.4 между картами).

## 📦 Модели (через симлинки из `/kaggle/input`)

### Flux2 Dev (GGUF)
- `flux2-dev-Q4_0.gguf` — основная модель (diffusion model)
- `mistral_3_small_flux2_fp8.safetensors` — текст-энкодер (CLIP)
- `flux2-vae.safetensors` — VAE

### LTX 2.3 Video (FP8)
- `ltx-2.3-22b-distilled-1.1-Q6_K.gguf` — основная модель
- `gemma-3-12b-it-heretic-fp4-comfy.safetensors` — текст-энкодер
- `ltx-2.3_text_projection_bf16.safetensors` — текст-проекция
- `LTX23_video_vae_bf16.safetensors` — видео-VAE
- `LTX23_audio_vae_bf16.safetensors` — аудио-VAE
- `taeltx2_3.safetensors` — VAE
- `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` — апскейлер
- `LTX-2.3-22b-AV-LoRA-talking-head-v1.safetensors` — LoRA (говорящая голова)
- `LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors` — LoRA
- `ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors` — LoRA 


## 🧩 Установленные ноды (по умолчанию)

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
| ComfyUI-Manager | Менеджер нод (ставится на шаге 1) |

## 🔧 Настройка под себя

- **Добавить ноду** — словарь `CUSTOM_NODES` в `instal_castom_node.py`
  (`"имя-папки": "git-url"`). Clone/pull и установка requirements — автоматически.
- **Добавить модель** — список `SYMLINKS` в `instal_castom_node.py`
  (кортеж `(источник_в_/kaggle/input, назначение_в_ComfyUI)`).
- **Общий pip-пакет** — `install_common_extras()` в `instal_comfyui.py`.
- **Флаги запуска ComfyUI** — метод `_start_comfy()` в `start.py`.

> 🔄 **Авто-обновление.** `start.py` при старте делает `git pull --ff-only` из
> этого репозитория — правки скриптов прилетают на Kaggle сами.

---

## 💖 Поддержать проект

Проект развивается силами **THE ANGEL AI** и остаётся бесплатным. Если он
сэкономил вам деньги на облаке или GPU — поддержите развитие, это помогает делать
новые инструменты:

### 👉 **[Поддержать на Boosty](https://boosty.to/the_angel/donate)**

## 🌐 Сообщество

Вопросы, гайды, анонсы и помощь по запуску — в нашей группе:

### 👉 **[THE ANGEL AI — ВКонтакте](https://vk.com/theangel_lab)**

---

<p align="center"><b>THE ANGEL AI</b> · сделано с ❤️ для тех, у кого нет своего GPU</p>
