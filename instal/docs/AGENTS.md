# Kaggle ComfyUI Launcher — Правила для агентов

## Архитектура

```
ComfyLauncher (launcher.py)
├── launch() — точка входа (вызывается из ячейки)
│   ├── Thread: _heartbeat_loop    (keep-alive #1: widgets.HTML)
│   ├── Thread: _stdout_keep_alive (keep-alive #2: stdout print)
│   ├── Thread: _startup           (запуск ComfyUI + туннель)
│   └── _keep_alive()              (осн. поток занят — Kaggle не усыпит)
│
├── _startup()
│   ├── _cleanup_old()       — pkill старых, чистка .db
│   ├── _check_git_updates() — git fetch/pull
│   ├── _check_files()       — venv, torch, ноды
│   ├── _ensure_cloudflared()
│   ├── _start_comfy()       — subprocess.Popen(main.py)
│   ├── _wait_for_port()     — socket на 127.0.0.1:8188
│   └── _start_tunnel()      — cloudflared tunnel
│
└── _on_stop() / _on_restart() — callback'и кнопок
```

**LogManager (logging_ui.py)**
- `LogManager.print(text)` — добавляет строку в буфер (thread-safe, deque maxlen=2000)
- `_log_flusher` (daemon thread) — раз в 0.5с: `html.escape()` → `widgets.HTML.value = <pre>...</pre>`
- Скролл — браузерное CSS scroll anchoring (overflow:auto). Без JS. Без авто-скролла.
- Кнопки — `widgets.Button` с `on_click`
- Панель собирается в `_build_ui()` и показывается через `display()`

---

## ⚠️ Жёсткие правила (нарушение = поломка)

### 1. `_keep_alive()` ОБЯЗАТЕЛЕН в launch()
Если `launch()` завершается — Kaggle видит, что ячейка простаивает >30 мин, и убивает сессию. `_keep_alive()` вызывается синхронно в конце `launch()` и блокирует поток.

**Внутри `_keep_alive()`: pump (обработка on_click) + sleep 0.05с.**
```python
def _keep_alive(self):
    pump = self._make_kernel_pump()
    while not self.stopped:
        if pump is not None:
            try:
                pump()
            except Exception:
                time.sleep(0.2)
        time.sleep(0.05)
```

### 2. `_make_kernel_pump()` — pump для on_click кнопок (ОБЯЗАТЕЛЕН)
Без pump кнопки `on_click` не обрабатываются, пока ячейка в `_keep_alive()`.

Использует **nest_asyncio**, чтобы выполнить async-корутину `kernel.do_one_iteration()` из синхронного цикла:

```python
def _make_kernel_pump(self):
    import nest_asyncio
    nest_asyncio.apply()
    loop = asyncio.get_event_loop()
    def pump():
        res = kernel.do_one_iteration()
        if asyncio.iscoroutine(res):
            loop.run_until_complete(res)
    return pump
```

**Если pump не создать (None):** кнопки не работают — только ⏹ Interrupt.

**История:** pump был в рабочем `start.py` с nest_asyncio, выброшен при рефакторинге в launcher.py — кнопки сломались. Вернули.

### 3. Лог — ТОЛЬКО `widgets.HTML`, НЕ `widgets.Output`
- ✅ `widgets.HTML.value = html` — работает из любого потока через iopub
- ✅ Scroll anchoring: браузер сам держит скролл. Если пользователь внизу — видит новые строки (scroll stays at bottom). Если читает выше — скролл не дёргается.
- ❌ `widgets.Output.append_stdout()` — авто-скроллит вниз на КАЖДЫЙ вызов, пользователь не может читать старые логи
- ❌ `sys.stdout.write()` — дублирует строки под виджетом
- ❌ `print()` в `LogManager.print()` — дублирует под виджетом

**Почему вернулись с Output на HTML (эволюция):**
1. HTML + per-line update → скролл прыгал наверх при каждой перерисовке
2. Output + per-line append_stdout → скролл прыгал вниз на каждую строку (iopub flood)
3. Output + buffer + 0.5s flusher → скролл прыгал вниз раз в 0.5с (лучше, но всё ещё мешает)
4. HTML + buffer + 0.5s flusher → **scroll anchoring работает, скролл НЕ прыгает**

**Куда выводить логи:**
```python
# Только в виджет — НЕ в stdout!
self.logger.print("[*] Сообщение")

# stdout — ТОЛЬКО для anti-sleep маяка (раз в 5 мин)
print("💓 keep-alive", flush=True)
```

### 4. Флаги ComfyUI (проверены, работают)
```python
comfy_args = [
    VENV_PYTHON, "main.py",
    "--listen", "0.0.0.0",
    "--port", str(PORT),
    "--enable-cors-header", "*",
    "--disable-auto-launch",
    "--preview-method", "auto",
    # Без attention-флага — ComfyUI использует torch SDPA (default на torch 2+)
]
```

- `--preview-method auto` — авто-превью в ComfyUI
- Attention: **SDPA (torch default)** — ✅ проверено: 720p видео (2 прохода) без OOM.
- `--use-split-cross-attention` — убран: вызывал `torch.OutOfMemoryError` на втором проходе 720p.
- Если OOM-killer (SIGKILL -9) при загрузке модели — вернуть `--use-split-cross-attention`.

### 4b. SageAttention-SM75 — НЕ ИСПОЛЬЗОВАТЬ
- **SageAttention НЕ РАБОТАЕТ с GGUF-моделями** (llama.cpp бэкенд, не диффузионный attention).
- GGUF-модели (LTX, Flux GGUF и т.д.) используют свой бэкенд attention — SageAttention не подменяет его.
- SageAttention имеет смысл только для диффузионных моделей (SD, SDXL, Flux fp16).
- Метод `_install_sage_attention()` в launcher.py оставлен для справки, но **не вызывается** в `_startup()`.

### 5. Другие флаги — НЕ ДОБАВЛЯТЬ
- `--fp16 / --bf16` — не нужны, ComfyUI сам выбирает точность
- `--xformers` — нестабильно на T4 с некоторыми нодами
- `--gpu-only` — CUDA illegal memory access (вытеснение из VRAM)
- `--force-fp16` — может сломать ноды с CPU-операциями

### 6. AIMDO — отключать ЧЕРЕЗ `os.environ`, НЕ `env=` в Popen
```python
# ✅ ПРАВИЛЬНО
os.environ["COMFY_AIMDO_ENABLED"] = "0"

# ❌ НЕПРАВИЛЬНО — ломает процесс (exit code 1, причина неизвестна)
proc = subprocess.Popen([...], env=dict(os.environ, COMFY_AIMDO_ENABLED="0"))
```

`comfy-aimdo` вызывает `hostbuf_file_reader_read failed` → `CUDA illegal memory access` на Kaggle.

---

## Потоки (все daemon=True)

| Поток | Откуда | Что делает |
|---|---|---|
| `_heartbeat_loop` | launch() | heartbeat в widgets.HTML каждые 30с |
| `_stdout_keep_alive` | launch() | пульс в stdout каждые 5 мин |
| `_startup` | launch() | весь pipeline (env, ноды, ComfyUI, туннель) |
| `stream_process` | _start_comfy() | читает stdout ComfyUI в лог |
| `_read_tunnel_output` | _start_tunnel() | читает stdout туннеля, ищет URL |
| `_log_flusher` | LogManager.__init__ | перерисовывает html-лог раз в 0.5с |

---

## История поломок

| Ошибка | Симптом | Фикс |
|---|---|---|
| widgets.Output с clear_output() | лог не обновляется | widgets.HTML.value = html |
| sys.stdout.write() в LogManager.print() | дубли строк под виджетом | убрать sys.stdout.write() |
| удалён _keep_alive() | Kaggle убивает сессию | вернуть sleep+flush |
| pump выброшен при рефакторинге start.py → launcher.py | кнопки on_click не работали | вернуть _make_kernel_pump с nest_asyncio |
| do_one_iteration() без nest_asyncio | RuntimeWarning: async | pump через nest_asyncio.apply() + loop.run_until_complete() |
| SageAttention-SM75 подключён в _startup() | не работает с GGUF (llama.cpp) | отключён вызов из _startup() |
| do_one_iteration() без nest_asyncio | RuntimeWarning: async | pump через nest_asyncio.apply() + loop.run_until_complete() |
| env={...} в Popen для AIMDO | процесс падает с code 1 | os.environ["COMFY_AIMDO_ENABLED"] = "0" |
| widgets.Output + append_stdout() | авто-скролл вниз на каждую строку | widgets.HTML + buffer + 0.5s flusher + scroll anchoring |
| --use-split-cross-attention | OOM на втором проходе 720p видео | убрать → SDPA (torch default) |
| --gpu-only | CUDA illegal memory access | убрать флаг |

---

## Контракт: что проверять перед коммитом

1. **Синтаксис:**
   ```
   python -c "compile(open('instal/launcher.py',encoding='utf-8').read(),'launcher.py','exec')"
   ```
2. **Нет RuntimeWarning/DeprecationWarning** в тестовом прогоне
3. **Логи — только в виджет:** нет sys.stdout.write / print в `LogManager.print()`
4. **Pump работает:** `_make_kernel_pump()` есть, `nest_asyncio` устанавливается при необходимости
5. **AIMDO отключён:** `os.environ["COMFY_AIMDO_ENABLED"] = "0"` на месте
6. **Флаги ComfyUI:** `--preview-method auto` в `_start_comfy()` (без attention-флага — SDPA)
7. **keep-alive:** `self._keep_alive()` — последний вызов в `launch()`
8. **Никаких новых флагов ускорения** без обоснования в этом файле
