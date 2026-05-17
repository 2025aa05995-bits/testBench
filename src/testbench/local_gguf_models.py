"""Local GGUF model family detection and llama.cpp load helpers."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

# Substrings in model filenames / paths (lowercase match).
_GEMMA3_MARKERS = ("gemma-3", "gemma3", "gemma_3")
_GEMMA2_MARKERS = ("gemma-2", "gemma2", "gemma_2")

# llama-cpp-python chat_format registry uses "gemma" for Gemma 2 and Gemma 3 text chat.
_LLAMA_CPP_GEMMA_CHAT_FORMAT = "gemma"

# Minimum version with Gemma 3 architecture support in bundled llama.cpp (see release notes).
MIN_LLAMA_CPP_VERSION: Tuple[int, int, int] = (0, 3, 23)


def _basename_lower(model_path: str) -> str:
    return os.path.basename(model_path or "").lower()


def is_gemma3_model_path(model_path: str) -> bool:
    """True when the path looks like a Gemma 3 GGUF (not Gemma 2)."""
    low = _basename_lower(model_path)
    if not any(m in low for m in _GEMMA3_MARKERS):
        return False
    # Avoid matching unrelated names that contain "gemma3" as substring of something else.
    return True


def is_gemma2_model_path(model_path: str) -> bool:
    low = _basename_lower(model_path)
    return any(m in low for m in _GEMMA2_MARKERS)


def detect_gguf_model_family(model_path: str) -> str:
    """Return a short family id for UI hints and defaults."""
    low = _basename_lower(model_path)
    if is_gemma3_model_path(model_path):
        return "gemma-3"
    if is_gemma2_model_path(model_path):
        return "gemma-2"
    if "gemma" in low:
        return "gemma"
    for tag in (
        "llama-3",
        "llama3",
        "llama-2",
        "mistral",
        "phi-3",
        "qwen",
        "deepseek",
        "kimi",
    ):
        if tag in low:
            return tag.replace("llama3", "llama-3")
    return "unknown"


def resolve_local_gguf_chat_format(model_path: str, explicit: str) -> str:
    """Map config/GUI ``chat_format`` to a value accepted by ``Llama(chat_format=...)``.

    ``gemma-3`` and ``auto`` on a Gemma 3 file both resolve to ``gemma`` (the registered
  llama-cpp-python template). Gemma 2 and legacy Gemma files use the same template.
    """
    fmt = str(explicit or "").strip().lower()
    if fmt in {"", "auto"}:
        family = detect_gguf_model_family(model_path)
        if family == "gemma-3":
            return _LLAMA_CPP_GEMMA_CHAT_FORMAT
        if family == "gemma-2" or family == "gemma":
            return _LLAMA_CPP_GEMMA_CHAT_FORMAT
        low = model_path.lower()
        for tag, resolved in (
            ("llama-3", "llama-3"),
            ("llama3", "llama-3"),
            ("llama-2", "llama-2"),
            ("mistral", "mistral-instruct"),
            ("phi-3", "phi-3"),
            ("qwen", "qwen"),
        ):
            if tag in low:
                return resolved
        return "chatml"
    if fmt in {"gemma-3", "gemma3", "gemma_3"}:
        return _LLAMA_CPP_GEMMA_CHAT_FORMAT
    return fmt


def gemma3_default_n_ctx() -> int:
    """Suggested context for Gemma 3 instruct models (large prompts in testBench)."""
    return 8192


def parse_version_tuple(version: str) -> Tuple[int, int, int]:
    parts: List[int] = []
    for piece in re.split(r"[^\d]+", version or ""):
        if not piece:
            continue
        parts.append(int(piece))
        if len(parts) >= 3:
            break
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


def llama_cpp_supports_gemma3() -> bool:
    try:
        import llama_cpp  # type: ignore

        ver = parse_version_tuple(getattr(llama_cpp, "__version__", "0.0.0"))
        return ver >= MIN_LLAMA_CPP_VERSION
    except Exception:
        return False


def gemma3_runtime_warning() -> Optional[str]:
    """Return a user-facing warning when Gemma 3 is likely unsupported, else None."""
    if llama_cpp_supports_gemma3():
        return None
    try:
        import llama_cpp  # type: ignore

        ver = getattr(llama_cpp, "__version__", "?")
    except Exception:
        ver = "?"
    min_ver = ".".join(str(x) for x in MIN_LLAMA_CPP_VERSION)
    return (
        f"Gemma 3 GGUF files need llama-cpp-python >= {min_ver} (installed: {ver}). "
        f"Upgrade with: pip install --upgrade --prefer-binary 'llama-cpp-python>={min_ver}'"
    )


def apply_gemma3_load_defaults(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Bump ``n_ctx`` for Gemma 3 when the configured window is small."""
    path = str(settings.get("model_path") or "")
    if not is_gemma3_model_path(path):
        return settings
    out = dict(settings)
    n_ctx = int(out.get("n_ctx", 4096) or 4096)
    if n_ctx < gemma3_default_n_ctx():
        out["n_ctx"] = gemma3_default_n_ctx()
    return out


def build_llama_kwargs(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Keyword arguments for ``llama_cpp.Llama(...)`` from resolved bench settings."""
    model_path = str(settings.get("model_path") or "")
    settings = apply_gemma3_load_defaults(settings)
    chat_format = resolve_local_gguf_chat_format(
        model_path, str(settings.get("chat_format") or "auto")
    )
    return {
        "model_path": model_path,
        "n_ctx": int(settings.get("n_ctx", 4096)),
        "n_threads": int(settings.get("n_threads", 4)),
        "n_gpu_layers": int(settings.get("n_gpu_layers", 0)),
        "n_batch": int(settings.get("n_batch", 256)),
        "chat_format": chat_format,
        "verbose": bool(settings.get("verbose", False)),
    }
