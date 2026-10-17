# Installed video models

- Official weights: [Wan-AI/Wan2.1-T2V-1.3B-Diffusers](https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B-Diffusers).
- Pinned revision: `0fad780a534b6463e45facd96134c9f345acfa5b` (19 required model/config/tokenizer files, approximately 28.9 GB).
- License: [Apache-2.0, official original model license](https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B/blob/main/LICENSE.txt). If redistributing weights, preserve required license/attribution notices; this tool keeps weights local.
- Inference implementation: [Hugging Face Diffusers Wan documentation](https://huggingface.co/docs/diffusers/api/pipelines/wan).
- Model author's implementation and intended resolution: [Wan-Video/Wan2.1](https://github.com/Wan-Video/Wan2.1).

The author reports 8.19 GB VRAM for its optimized 1.3B implementation. This helper uses Diffusers with CPU offload; actual peak memory and speed depend on clip size and available RAM. The source checkpoint stores some weights at float32 on disk; inference casts the transformer and text encoder to bfloat16.

The helper downloads only safetensors, tokenizer files, and configuration from the pinned model. No repository Python code is downloaded or executed. The local download receipt records file sizes and official LFS SHA-256 hashes; `doctor --verify` rehashes all large files.

Validated runtime: Windows, Python 3.13.7, PyTorch 2.7.0+cu128, Diffusers 0.35.2, Transformers 4.57.6, and Accelerate 1.11.0. The project environment can reuse base Python packages, including the existing CUDA PyTorch, while installing pinned video dependencies into its own environment. The base Python installation is not modified. The local `environment-lock.txt` records the complete installed package versions.

Verified on the RTX 5080 Laptop GPU: the `preview` preset produced a 49-frame, 512 x 288 MP4 at 16 fps (3.06 seconds). The helper reported 112.46 seconds including model loading and 10.81 GiB peak allocated VRAM. Decoded frame count, dimensions, fps, and visible motion were checked, and representative frames were inspected. This is a preview benchmark; the 480p standard preset takes longer.

## Continuous-scene model

- Additional weights: [Wan-AI/Wan2.1-VACE-1.3B-diffusers](https://huggingface.co/Wan-AI/Wan2.1-VACE-1.3B-diffusers), revision `ec4d2cb062b548996b179d493fdd05340de702a1`.
- Only its transformer is downloaded: four files, approximately 7.15 GB, with the official weight SHA-256 values verified. It reuses the local base model's tokenizer, UMT5 text encoder (cast to bfloat16), scheduler, and VAE. Encoder/tokenizer configuration compatibility was checked; the VAE weight checksum matches exactly.
- License: [Apache-2.0](https://huggingface.co/Wan-AI/Wan2.1-VACE-1.3B/blob/main/LICENSE.txt).
- The installed Diffusers 0.35.2 `WanVACEPipeline` supports previous video and generation masks. The helper releases the text encoder before VAE conditioning to limit GPU memory usage, then reuses the pipeline for a batch of segments.
- Usage and continuity review: [continuous-video.md](continuous-video.md).
