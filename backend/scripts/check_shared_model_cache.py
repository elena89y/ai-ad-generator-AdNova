"""Check which model repos are available in the configured shared cache."""
from __future__ import annotations

import os
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download


REPOS = [
    ("black-forest-labs/FLUX.1-Fill-dev", "current"),
    ("black-forest-labs/FLUX.1-Kontext-dev", "current"),
    ("QuantStack/FLUX.1-Kontext-dev-GGUF", "current"),
    ("diffusers/stable-diffusion-xl-1.0-inpainting-0.1", "legacy"),
    ("stabilityai/stable-diffusion-xl-base-1.0", "legacy"),
    ("SG161222/RealVisXL_V5.0", "optional"),
    ("Qwen/Qwen3-VL-2B-Instruct", "optional"),
    ("Salesforce/blip-image-captioning-base", "optional"),
]


def main() -> int:
    print(f"HF_HUB_CACHE={os.environ.get('HF_HUB_CACHE', '')}")
    print(f"U2NET_HOME={os.environ.get('U2NET_HOME', '')}")
    u2net = Path(os.environ.get("U2NET_HOME", "")) / "birefnet-general.onnx"
    print(f"{'OK' if u2net.is_file() else 'MISS'} current rembg/birefnet-general.onnx")

    for repo, kind in REPOS:
        try:
            snapshot_download(repo, local_files_only=True)
            print(f"OK {kind} {repo}")
        except Exception as e:  # noqa: BLE001
            print(f"MISS {kind} {repo} {type(e).__name__}")

    try:
        hf_hub_download(
            "QuantStack/FLUX.1-Kontext-dev-GGUF",
            "flux1-kontext-dev-Q4_K_M.gguf",
            local_files_only=True,
        )
        print("OK current QuantStack/flux1-kontext-dev-Q4_K_M.gguf")
    except Exception as e:  # noqa: BLE001
        print(f"MISS current QuantStack/flux1-kontext-dev-Q4_K_M.gguf {type(e).__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
