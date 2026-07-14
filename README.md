# 🎬 LTX 2.3 ComfyUI — Kaggle Workspace (2×T4 GPU)

One-click ComfyUI setup for **LTX 2.3 video generation** on Kaggle with dual T4 GPUs.

## Quick Start

1. Create a new Kaggle notebook
2. Enable **GPU × 2** (Settings → Accelerator → 2× GPU)
3. Add [this dataset](https://www.kaggle.com/datasets/martasteiner/ltx-2-3-22b-distilled-1-1-q6-k-gguf) to your session
4. Paste this in a code cell:

```python
import sys
from IPython.display import clear_output, display, HTML

def print_status(message):
    display(HTML(f"<h2 style='color: green;'>✅ {message}</h2>"))

%cd /kaggle/working/
!git clone https://github.com/shtefand23/Kaggle_LTX23_ComfyUI.git
clear_output()
%cd /kaggle/working/Kaggle_LTX23_ComfyUI/instal
print_status("Auto-update built-in...")
%run start.py
```

5. Wait for the Cloudflare tunnel URL → open ComfyUI

## Workflows

| Workflow | Description |
|----------|-------------|
| `LTX23Legacy.json` | Standard LTX 2.3 video generation with audio support |
| `LTX23LTXDirector13.json` | LTX Director v1.3 — guided video with reference images |
| `LTX23LTXDirector2.json` | LTX Director v2 — advanced guided video generation |

## What Gets Installed

- **ComfyUI** + ComfyUI-Manager
- **15 custom nodes** including:
  - `ComfyUI-LTX2-MultiGPU` — Hybrid Split Loader for LTX 2.3 GGUF on 2×T4
  - `ComfyUI-MultiGPU` — Official DisTorch2 multi-GPU support
  - `ComfyUI-VideoHelperSuite` — Video/audio loading and combining
  - `ComfyUI-GGUF` — GGUF model loading
  - `ComfyUI-RIFE` — Frame interpolation
  - And more (see `instal/instal_castom_node.py` for full list)

## Models (from [Kaggle dataset](https://www.kaggle.com/datasets/martasteiner/ltx-2-3-22b-distilled-1-1-q6-k-gguf))

- `ltx-2.3-22b-distilled-1.1-Q6_K.gguf` — LTX 2.3 22B GGUF (diffusion model)
- `ltx-2.3-22b-distilled-1.1-UD-Q5_K_M.gguf` — LTX 2.3 22B GGUF Q5 (lighter)
- `gemma-3-12b-it-UD-Q5_K_XL.gguf` — Gemma 3 12B text encoder (GGUF)
- `ltx-2.3_text_projection_bf16.safetensors` — Text projection
- `LTX23_video_vae_bf16.safetensors` — Video VAE
- `LTX23_audio_vae_bf16.safetensors` — Audio VAE
- `taeltx2_3.safetensors` — Alternative VAE
- `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` — Spatial upscaler
- Various LoRAs (talking head, NFT, IC-LoRA)

## Credits

- [THE-ANGEL-AI](https://github.com/THE-ANGEL-AI/Kaggle_Workspace) — Original workspace
- [LTX 2.3](https://github.com/Lightricks/LTX-Video) — Video generation model
