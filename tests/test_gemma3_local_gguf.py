"""Gemma 3 local GGUF detection and optional live load test."""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from testbench.local_gguf_models import (
    apply_gemma3_load_defaults,
    detect_gguf_model_family,
    gemma3_default_n_ctx,
    is_gemma3_model_path,
    llama_cpp_supports_gemma3,
    resolve_local_gguf_chat_format,
)
from testbench.llm_chat import _local_gguf_run_oneshot, _local_gguf_settings


def test_detect_gemma3_family():
    assert detect_gguf_model_family("C:/models/gemma-3-4b-it-Q4_K_M.gguf") == "gemma-3"
    assert detect_gguf_model_family("C:/models/google_gemma3-1b-it.gguf") == "gemma-3"
    assert detect_gguf_model_family("C:/models/gemma-2-2b-it-Q4_K_M.gguf") == "gemma-2"


def test_is_gemma3_model_path():
    assert is_gemma3_model_path("/x/gemma-3-1b-it-Q4_K_M.gguf")
    assert not is_gemma3_model_path("/x/gemma-2-2b-it-Q4_K_M.gguf")


def test_resolve_gemma3_chat_format_to_gemma():
    assert resolve_local_gguf_chat_format("/m/gemma-3-4b.gguf", "auto") == "gemma"
    assert resolve_local_gguf_chat_format("/m/other.gguf", "gemma-3") == "gemma"
    assert resolve_local_gguf_chat_format("/m/llama-random.gguf", "auto") == "chatml"


def test_apply_gemma3_load_defaults_bumps_n_ctx():
    s = apply_gemma3_load_defaults(
        {"model_path": "C:/m/gemma-3-1b-it.gguf", "n_ctx": 2048, "chat_format": "gemma"}
    )
    assert s["n_ctx"] >= gemma3_default_n_ctx()


def test_local_gguf_settings_gemma3_auto():
    s = _local_gguf_settings(
        {
            "local_gguf": {
                "model_path": "C:/models/gemma-3-12b-it-Q4_K_M.gguf",
                "chat_format": "auto",
                "n_ctx": 4096,
            }
        }
    )
    assert s["chat_format"] == "gemma"
    assert s["n_ctx"] >= gemma3_default_n_ctx()


def _gemma3_gguf_path() -> str:
    env = os.environ.get("TESTBENCH_GEMMA3_GGUF", "").strip()
    if env:
        return env
    for candidate in (
        Path("C:/git/models/gemma-3-4b-it-Q4_K_M.gguf"),
        ROOT.parent / "models" / "gemma-3-4b-it-Q4_K_M.gguf",
        ROOT.parent / "models" / "gemma-3-1b-it-Q4_K_M.gguf",
        Path("C:/git/models/gemma-3-1b-it-Q4_K_M.gguf"),
    ):
        if candidate.is_file():
            return str(candidate)
    return str(Path("C:/git/models/gemma-3-1b-it-Q4_K_M.gguf"))


@pytest.mark.integration
def test_gemma3_subprocess_ping_if_model_present():
    """Load a real Gemma 3 GGUF in the isolated worker when the file exists."""
    if not llama_cpp_supports_gemma3():
        pytest.skip("llama-cpp-python too old for Gemma 3")
    path = _gemma3_gguf_path()
    if not os.path.isfile(path):
        pytest.skip(f"Gemma 3 GGUF not found at {path!r} (set TESTBENCH_GEMMA3_GGUF)")

    settings = _local_gguf_settings(
        {
            "local_gguf": {
                "model_path": path,
                "chat_format": "gemma-3",
                "n_ctx": 2048,
                "n_gpu_layers": 0,
                "n_threads": 0,
            }
        }
    )
    assert settings["chat_format"] == "gemma"
    text = _local_gguf_run_oneshot(settings, {"op": "ping"}, wall_timeout=300.0)
    assert text.strip().upper().startswith("OK") or len(text.strip()) >= 1
