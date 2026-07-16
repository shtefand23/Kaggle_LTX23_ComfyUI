# 🎬 LTX 2.3 Director V2 Beta — Kaggle Workspace (2×T4 GPU)

One-click ComfyUI setup for **LTX 2.3 Director V2 Beta** on Kaggle with dual T4 GPUs.

## Quick Start

1. Create a new Kaggle notebook
2. Enable **GPU × 2** (Settings → Accelerator → 2× GPU)
3. Add [this dataset](https://www.kaggle.com/datasets/martasteiner/ltxdirector) to your session (all 19 models)
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
| `LTX_Director-V2-Beta.json` | LTX Director V2 Beta — full featured video generation |
| `LTX23Legacy.json` | Standard LTX 2.3 video generation with audio support |
| `LTX23LTXDirector13.json` | LTX Director v1.3 — guided video with reference images |
| `LTX23LTXDirector2.json` | LTX Director v2 — advanced guided video generation |

## What Gets Installed

- **ComfyUI** + ComfyUI-Manager
- **16 custom nodes** including:
  - `ComfyUI-LTX2-MultiGPU` — Hybrid Split Loader for LTX 2.3 GGUF on 2×T4
  - `ComfyUI-MultiGPU` — Official DisTorch2 multi-GPU support
  - `ComfyUI-VideoHelperSuite` — Video/audio loading and combining
  - `ComfyUI-GGUF` — GGUF model loading
  - `ComfyUI-RIFE` — Frame interpolation
  - `ComfyUI-AcademiaSD` — Auto model downloader
  - And more (see `instal/instal_castom_node.py` for full list)

## Models (from [Kaggle dataset](https://www.kaggle.com/datasets/martasteiner/ltxdirector))

### Diffusion Models
- `ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors` (23.49 GB)
- `ltx-2.3-22b-distilled-1.1-UD-Q5_K_M.gguf` (16.96 GB, lighter alternative)

### Text Encoders
- `gemma_3_12B_it_fp8_scaled.safetensors` (12.3 GB)
- `ltx-2.3_text_projection_bf16.safetensors` (2.15 GB)

### VAE
- `LTX23_video_vae_bf16.safetensors`
- `LTX23_audio_vae_bf16.safetensors`
- `taeltx2_3.safetensors`

### Upscaler
- `ltx-2.3-spatial-upscaler-x2-1.1.safetensors`

### LoRAs
- `ltx-2.3-22b-distilled-1.1_lora-dynamic_fro09_avg_rank_111_bf16.safetensors`
- `LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors`

### IC LoRAs
- `ltx-2.3-22b-ic-lora-cross-eyed-0.9.safetensors`
- `ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors`
- `ltx-2-19b-ic-lora-detailer.safetensors`
- `lora_weights_step_12000.safetensors`
- `ltx2.3_upscale_ic-lora_06250.safetensors`
- `ltx-2.3-22b-ic-lora-lipdub-0.9.safetensors`
- `ltx2.3_audio_reactive_lora_v2.safetensors`
- `ltx-2.3-22b-ic-lora-hdr-0.9.safetensors`
- `ltx-2.3-22b-ic-lora-decompression-0.9.safetensors`

## Credits

- [THE-ANGEL-AI](https://github.com/THE-ANGEL-AI/Kaggle_Workspace) — Original workspace
- [WhatDreamsCost](https://www.youtube.com/@WhatDreamsCost/) — LTX Director V2 Beta workflow
- [LTX 2.3](https://github.com/Lightricks/LTX-Video) — Video generation model
