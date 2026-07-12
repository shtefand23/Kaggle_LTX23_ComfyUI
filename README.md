# ☁️ Kaggle Cloud — ComfyUI on Free 2× Tesla T4

> Project **[THE ANGEL AI](https://vk.com/theangel_lab)** — running heavy
> generative **ComfyUI** pipelines (Flux2 GGUF, LTX 2.3 Video, TTS) directly in
> a free Kaggle notebook on **two Tesla T4**, with no local GPU and no cloud billing.

[![Support the project](https://img.shields.io/badge/💖_Support-Boosty-f15f2c?style=for-the-badge)](https://boosty.to/the_angel/donate)
[![VK](https://img.shields.io/badge/Community-VK-0077FF?style=for-the-badge&logo=vk)](https://vk.com/theangel_lab)

---

## 🎯 What This Is and Why

Kaggle gives you **2× Tesla T4 (16 GB each) for 30 hours per week** for free — that's
enough to run Flux2, video pipelines, and TTS. But a "naked" Kaggle is painful:

- ❌ Environment breaks after every session restart
- ❌ Binaries lose execute bit (`+x`) — files are there but won't run
- ❌ When Kaggle updates the kernel, old Python is incompatible with the new libc
- ❌ Multi-GPU (2× T4) conflicts without proper configuration
- ❌ After 40 minutes of inactivity, Kaggle puts the session to sleep

**This repository turns the launch into a single line and fixes everything automatically.**

---

## 📂 Structure

```
Kaggle_Workspace_FreeGPU/
├─ README.md                  # this file
├─ instal/                    # ☕ core: installation and launch scripts
│  ├─ instal_comfyui.py       #   STEP 1: uv + venv + torch cu130 + ComfyUI
│  ├─ instal_castom_node.py   #   STEP 2: custom nodes + models
│  ├─ start.py                #   STEP 3: launch + tunnel + panel + keep-alive
│  └─ kaggle_env.py           #   engine: paths, uv, venv repair, diagnostics
├─ Notebook/                  # 📓 ready-to-import Kaggle notebooks
│  ├─ confyui-main.ipynb
│  └─ gemma_kaggle_server.ipynb
├─ workflows/                 # 🎨 ComfyUI workflows (drag-n-drop import)
│  ├─ Flux2dev32b_GGUF.json
│  ├─ Flux2dev32b_GGUF v2 API.json
│  └─ LTX_Director-V2-Beta.json
├─ docs-site/                 # 🌐 documentation site (GitHub Pages)
└─ _kaggle_tests/             # 🧪 tests for Kaggle verification
```

---

## 🚀 Quick Start

Open a Kaggle notebook, enable **GPU T4 ×2** and internet, run in order:

```python
# 0. Get the scripts (first time — clone, then — pull)
!git clone https://github.com/THE-ANGEL-AI/Kaggle_Workspace_FreeGPU.git || \
 git -C Kaggle_Workspace_FreeGPU pull

# 1. ComfyUI + Manager
!python Kaggle_Workspace_FreeGPU/instal/instal_comfyui.py

# 2. Custom nodes + models
!python Kaggle_Workspace_FreeGPU/instal/instal_castom_node.py

# 3. Launch + Cloudflare tunnel + control panel
%run Kaggle_Workspace_FreeGPU/instal/start.py
```

> 💡 **You can do it in one line.** `start.py` will check the environment itself, install
> what's missing, and launch everything. For a cold start, `%run .../instal/start.py` is enough.

After step 3, buttons will appear under the cell:

| Button | What it does |
|--------|-------------|
| 🔗 **Open ComfyUI** | Public Cloudflare link (new one for each launch) |
| 🛑 **Stop** | Shuts down ComfyUI and tunnel without restarting the kernel |
| 🔄 **Restart** | Brings ComfyUI back up (new URL) |

---

## 🏗️ Architecture: Three Steps

| Step | File | What it installs / does | Run |
|------|------|------------------------|-----|
| 1 | `instal_comfyui.py` | uv + venv (Python 3.12) + torch cu130 + ComfyUI + Manager + common packages | `!python instal/instal_comfyui.py` |
| 2 | `instal_castom_node.py` | 8 custom nodes from list + model symlinks from `/kaggle/input` + auto-inject SageAttention-T4 into workflow | `!python instal/instal_castom_node.py` |
| 3 | `start.py` | Environment check/repair → build SageAttention-SM75 + node symlink → ComfyUI → Cloudflare tunnel → button panel → keep-alive | `%run instal/start.py` |
| — | `kaggle_env.py` | **System core**: paths, uv, venv creation/repair/diagnostics, `install_python()` | imported by all |

---

## 🛡️ Self-Healing: How the Environment Fixes Itself

**Problem.** Kaggle on session restart:
1. 🧨 **Resets the `+x` bit** — files are in place but won't execute
2. 🧨 **Updates the OS kernel** — old CPython (compiled against a different libc) fails on launch. The file exists but can't be run.

**How this is fixed (3 levels, by increasing cost):**

```
venv broken?
 ├─ 🔧 Level 1 — restore +x (one second)
 │   If venv/bin/python and base CPython just lost the execute bit —
 │   chmod 755 fixes everything in milliseconds. Torch is untouched.
 │
 ├─ 🔧 Level 2 — reinstall base CPython (10-30 seconds)
 │   If +x didn't help — Kaggle updated the kernel. Old CPython
 │   is incompatible with the new libc → we remove it and install
 │   a fresh one via uv. Packages in venv are still alive (but the
 │   symlink is broken, venv still doesn't work).
 │
 └─ 🔧 Level 3 — recreate venv + torch (from cache — fast)
     Old venv is deleted, new one created on fresh CPython.
     Torch and packages are reinstalled from uv cache — not downloaded
     again. After this, start.py automatically reinstalls node dependencies.
```

<details>
<summary><b>🔬 Technical: How It Works</b></summary>

```python
def install_python():
    """Single entry point: uv + venv (created/repaired/recreated)
       Returns: True if everything was already working, False if repair happened
    """
    ensure_uv()
    return ensure_venv()

def venv_python_ok():
    """Check by actually running, not os.path.exists"""
    subprocess.run([VENV_PYTHON, "-c", "pass"],
                   check=True, capture_output=True, timeout=30)

def repair_venv_perms():
    """Level 1: quickly fixes +x on everything executable"""
    candidates = [venv/bin/python, real CPython, uv, python3*]
    for c in candidates: os.chmod(c, 0o755)

def repair_base_python_via_uv():
    """Level 2: CPython incompatible with kernel — reinstall"""
    shutil.rmtree(UV_PYTHON_DIR)
    run(["uv", "python", "install", "3.12"])

def ensure_venv():
    """Level 3: uv venv --clear (packages from cache), returns flag"""
    if venv_python_ok(): return True   # all good
    if repair_venv_perms(): return False  # +x fixed it
    repair_base_python_via_uv()
    run(["uv", "venv", ... "--clear"])
    return False  # was recreated — torch may be gone
```
</details>

### 🩺 Diagnostics: Why It Broke

If venv doesn't work — the script will **exactly tell you the reason** in the log:

| Symptom | Diagnosis | What the script does |
|---------|-----------|---------------------|
| `No such file or directory` | Broken symlink — `venv/bin/python` points to nothing | Recreates venv |
| `Permission denied` | Lost `+x` bit | chmod 755 (one second) |
| `version GLIBC_2.38 not found` | Kaggle updated kernel, old CPython incompatible | `uv python install` (fresh CPython) |
| `FATAL: kernel too old` | OS kernel newer than what CPython was compiled for | Same — reinstall CPython |

---

## 🔒 Kaggle Anti-Sleep Protection

**Problem.** Kaggle after ~40 minutes of inactivity shows *"Are you still there?"*
and may stop the session, especially if the tab is minimized.

**How we solved this:**

```
2 independent keep-alive layers working in parallel:

┌─────────────────────────────────────────────────────┐
│ 🖥️  Layer 1: Heartbeat widget (every 30 seconds)    │
│    Updates an HTML string in the control panel.      │
│    Creates traffic browser → Kaggle sees activity    │
│    and doesn't touch the session.                    │
│    Lives as long as the tab is open.                 │
├─────────────────────────────────────────────────────┤
│ 📢  Layer 2: Stdout pulse (every 5 minutes)          │
│    Prints 💓 [14:32:01] ComfyUI active... directly   │
│    to the cell stdout via print(flush=True).         │
│    Guaranteed to send data to Kaggle servers even    │
│    if the tab is minimized — doesn't depend on the   │
│    browser. Prevents "Are you still there?".         │
└─────────────────────────────────────────────────────┘
```

<details>
<summary><b>🔬 Technical: Two threads in start.py</b></summary>

```python
def launch(self):
    Thread(target=self._heartbeat_loop, daemon=True).start()    # widget, 30s
    Thread(target=self._stdout_keep_alive, daemon=True).start() # stdout, 5 min
    Thread(target=self._startup, daemon=True).start()
    self._keep_alive()  # main cell loop (keeps kernel active)

def _stdout_keep_alive(self):
    print("🔒 [PROTECTION] Kaggle protection system activated!", flush=True)
    while not self.stopped:
        time.sleep(300)
        now = datetime.now().strftime("%H:%M:%S")
        print(f"💓 [{now}] ComfyUI active, waiting for request...", flush=True)
```
</details>

---

## ⚡ What's Optimized for T4 Speed

| Optimization | Why |
|-------------|-----|
| **uv instead of pip** | Parallel package installation, torch installs much faster |
| **torch cu130** | CUDA 13.0 — Kaggle driver 580.x supports it; cu128 had a warning and slower path |
| **SageAttention-SM75** 🆕 | **Custom CUDA kernel** for T4 (Turing): INT8 QK + FP16 PV + FP32 accum. Up to **2.5×** attention on long contexts. Works as a ComfyUI custom node (`SageAttention-T4 Apply`) — via `add_object_patch()`, no global monkey-patches and no launch flags |
| **No xformers** | Incompatible with T4 (sm_75). Previously fell back to `--use-pytorch-cross-attention`, now uses `--use-split-cross-attention` |
| **ComfyUI-MultiGPU** | DisTorch2 instead of the old ComfyBootlegOffload hack (they conflicted) |
| **No tensorflow / old pins** | They pull their own CUDA versions, breaking modern nodes |
| **smart-memory enabled** | Model is cached in VRAM between generations |
| **uv cache in /kaggle/working** | Wheels (torch etc.) survive restarts — reinstall from cache, not network |

---

## 🧠 SageAttention-SM75 — Accelerated Attention on T4

SageAttention-SM75 is a **custom CUDA kernel** for NVIDIA Turing (T4, sm_75)
that replaces standard PyTorch attention with a quantized implementation:

| Component | Precision | Purpose |
|-----------|-----------|---------|
| Q·K matmul | INT8 | 4× less memory, faster compute on Turing tensor cores |
| Softmax | FP32 | Numerical stability |
| Attention × V | FP16 | Matches T4's native format |
| Output accumulator | FP32 | Prevents overflow |

**Performance:** Up to **2.5× faster** on long sequences (high-res images, long videos).

**How it works:**
- Installed as a ComfyUI custom node (`SageAttention-T4`)
- Activated via `add_object_patch()` on the model — no global monkey-patches
- Falls back gracefully to `split-cross-attention` if installation fails
- Only activates when `--use-sage-attention` flag is present

---

## 📝 Workflow Files

Pre-built ComfyUI workflows are in the `workflows/` directory:

| Workflow | Description |
|----------|-------------|
| `Flux2dev32b_GGUF.json` | Flux2 Dev 32B quantized — text-to-image |
| `Flux2dev32b_GGUF v2 API.json` | Flux2 Dev with API interface |
| `LTX_Director-V2-Beta.json` | LTX 2.3 video generation |

Import them into ComfyUI via drag-n-drop after launching.

---

## 🧪 Testing

The `_kaggle_tests/` directory contains scripts for verifying the installation on Kaggle:

```bash
# Run all tests
!python _kaggle_tests/run_all.py
```

---

## 📄 License

MIT — use freely, modify freely. If this helps you, consider supporting the project.

---

## 🤝 Contributing

Issues and PRs welcome. For major changes, open an issue first.

---

## 🙏 Credits

- **[THE ANGEL AI](https://vk.com/theangel_lab)** — project author
- **[Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI)** — the node-based UI
- **[ltdrdata/ComfyUI-Manager](https://github.com/ltdrdata/ComfyUI-Manager)** — node manager
- **[THE-ANGEL-AI/SageAttention-SM75-path](https://github.com/THE-ANGEL-AI/SageAttention-SM75-path)** — Turing attention fork
- **[pollockjj/ComfyUI-MultiGPU](https://github.com/pollockjj/ComfyUI-MultiGPU)** — multi-GPU support
- **[Cloudflare](https://www.cloudflare.com/)** — free tunnel for public access
