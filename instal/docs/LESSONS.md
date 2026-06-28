# Уроки дня — 28 июня 2026

## Что ломалось и как чинили

1. **Pump с nest_asyncio — обязателен.** Без него `Kernel.do_one_iteration()` (async корутина) из синхронного кода не вызывается — RuntimeWarning. Решение: `nest_asyncio.apply()` + `loop.run_until_complete(res)`.

2. **При рефакторинге — не выбрасывать сложные механизмы.** `_make_kernel_pump()` был в рабочем `start.py`, выброшен при разбивке на модули → кнопки сломались.

3. **Порядок проверок в `_wait_for_port()`:** сначала порт (socket), потом `comfy_proc.poll()`. Иначе race condition при restart → false positive SIGKILL.

4. **SDPA (torch default)** — работает на T4, 720p 2 прохода без OOM. Медленно на GGUF.

5. **SageAttention** — НЕ работает с GGUF. Только для диффузионных моделей.

6. **CUDA 13 (cu130)** — наша версия, не cu124.

7. **llamacpp_gguf_cuda wheel** — не под Python 3.12 (wheel под 3.11). И не для ComfyUI (часть WanGP).

## Правила на будущее

- Перед коммитом — полный чеклист из AGENTS.md (8 пунктов).
- Не говорить "не будет работать" не проверив свой стек.
- Если пользователь про конфиг — читать instal_comfyui.py / kaggle_env.py.
