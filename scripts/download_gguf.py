"""Download a GGUF model from Hugging Face with resume + progress.

Usage:
  python scripts/download_gguf.py <hf_url> <dest_path>

Streams the response to disk in chunks, supports HTTP-range resume if a
partial file is present, and validates the downloaded file starts with the
``GGUF`` magic before returning success.
"""
from __future__ import annotations

import os
import sys
import time
import urllib.request
import urllib.error


CHUNK = 1 << 20  # 1 MiB


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0:
            return f"{n:6.1f} {unit}"
        n /= 1024.0
    return f"{n:6.1f} PB"


def download(url: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    existing = os.path.getsize(dest) if os.path.isfile(dest) else 0

    req = urllib.request.Request(url, headers={"User-Agent": "testbench/1.0"})
    if existing > 0:
        req.add_header("Range", f"bytes={existing}-")

    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        if e.code == 416 and existing > 0:
            print(f"Already complete: {dest} ({_human(existing)})")
            return
        raise

    status = resp.status
    cl = resp.headers.get("Content-Length")
    total = int(cl) if cl else 0
    if status == 206:
        total += existing
        mode = "ab"
        downloaded = existing
        print(f"Resuming from {_human(existing)} of {_human(total) if total else '?'}: {dest}")
    else:
        if existing > 0:
            print(f"Server ignored Range; restarting download of {dest}")
            existing = 0
        downloaded = 0
        mode = "wb"
        print(f"Downloading {_human(total) if total else 'unknown size'} -> {dest}")

    t0 = time.time()
    last_print = 0.0
    with open(dest, mode) as f:
        while True:
            chunk = resp.read(CHUNK)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            now = time.time()
            if now - last_print >= 1.0:
                last_print = now
                rate = (downloaded - existing) / max(1e-6, now - t0)
                if total:
                    pct = downloaded * 100 / total
                    print(
                        f"  {pct:5.1f}%  {_human(downloaded)} / {_human(total)}  "
                        f"@ {_human(rate)}/s",
                        flush=True,
                    )
                else:
                    print(f"  {_human(downloaded)}  @ {_human(rate)}/s", flush=True)
    elapsed = time.time() - t0
    final_size = os.path.getsize(dest)
    print(
        f"Done: {dest}  size={_human(final_size)}  in {elapsed:.1f}s  "
        f"avg={_human((final_size - existing) / max(1e-6, elapsed))}/s"
    )

    with open(dest, "rb") as f:
        magic = f.read(4)
    if magic != b"GGUF":
        raise SystemExit(
            f"Downloaded file does not start with GGUF magic (got {magic!r}); "
            "the download may be corrupted."
        )


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    download(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()

# python scripts/download_gguf.py ^
#   "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf" ^
#   "C:\git\models\Qwen2.5-7B-Instruct-Q4_K_M.gguf"
#
# Gemma 3 (needs llama-cpp-python >= 0.3.23):
# python scripts/download_gguf.py ^
#   "https://huggingface.co/ggml-org/gemma-3-1b-it-GGUF/resolve/main/gemma-3-1b-it-Q4_K_M.gguf" ^
#   "C:\git\models\gemma-3-1b-it-Q4_K_M.gguf"
#
# Gemma 3 4B instruct (recommended for local plans):
# python scripts/download_gguf.py ^
#   "https://huggingface.co/unsloth/gemma-3-4b-it-GGUF/resolve/main/gemma-3-4b-it-Q4_K_M.gguf" ^
#   "C:\git\models\gemma-3-4b-it-Q4_K_M.gguf"
