"""Unit tests for provider resolution, endpoint normalization, and local-GGUF settings."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from testbench.llm_chat import (
    PROVIDER_AZURE,
    PROVIDER_LOCAL_GGUF,
    PROVIDER_OPENAI,
    _local_gguf_settings,
    _normalize_azure_endpoint,
    _resolve_provider,
)


def test_normalize_azure_endpoint_strips_path_and_query():
    full = (
        "https://2025a-moub30vv-eastus2.cognitiveservices.azure.com"
        "/openai/deployments/gpt-4o/chat/completions?api-version=2025-01-01-preview"
    )
    assert (
        _normalize_azure_endpoint(full)
        == "https://2025a-moub30vv-eastus2.cognitiveservices.azure.com"
    )


def test_normalize_azure_endpoint_keeps_simple_base():
    base = "https://my-resource.openai.azure.com"
    assert _normalize_azure_endpoint(base) == base
    assert _normalize_azure_endpoint(base + "/") == base


def test_normalize_azure_endpoint_handles_blank():
    assert _normalize_azure_endpoint("") == ""
    assert _normalize_azure_endpoint("   ") == ""


def test_resolve_provider_aliases():
    assert _resolve_provider({"llm": {"provider": "azure_openai"}}) == PROVIDER_AZURE
    assert _resolve_provider({"llm": {"provider": "AZURE"}}) == PROVIDER_AZURE
    assert _resolve_provider({"llm": {"provider": "openai"}}) == PROVIDER_OPENAI
    assert _resolve_provider({"llm": {"provider": "openai_api"}}) == PROVIDER_OPENAI
    assert _resolve_provider({"llm": {"provider": "local_gguf"}}) == PROVIDER_LOCAL_GGUF
    assert _resolve_provider({"llm": {"provider": "local"}}) == PROVIDER_LOCAL_GGUF
    assert _resolve_provider({"llm": {"provider": "gguf"}}) == PROVIDER_LOCAL_GGUF
    assert _resolve_provider({"llm": {"provider": "llama_cpp"}}) == PROVIDER_LOCAL_GGUF
    assert _resolve_provider({"llm": {"provider": ""}}) == PROVIDER_AZURE
    assert _resolve_provider({}) == PROVIDER_AZURE


def test_local_gguf_settings_defaults_and_clamps():
    s = _local_gguf_settings({})
    assert s["model_path"] in ("", s["model_path"])
    assert 256 <= s["n_ctx"] <= 131072
    assert -1 <= s["n_gpu_layers"] <= 200
    assert 1 <= s["n_threads"] <= 128
    assert 16 <= s["max_tokens"] <= 32768
    assert s["chat_format"] in {"chatml", "gemma", "llama-3", "llama-2", "mistral-instruct", "phi-3", "qwen"}


def test_local_gguf_settings_chat_format_auto_picks_gemma():
    s = _local_gguf_settings({
        "local_gguf": {
            "model_path": "C:/models/gemma-2-2b-it-Q4_K_M.gguf",
            "chat_format": "auto",
        }
    })
    assert s["chat_format"] == "gemma"


def test_local_gguf_settings_explicit_chat_format_kept():
    s = _local_gguf_settings({
        "local_gguf": {
            "model_path": "/x/anything.gguf",
            "chat_format": "chatml",
        }
    })
    assert s["chat_format"] == "chatml"


def test_local_gguf_settings_clamps_out_of_range():
    s = _local_gguf_settings({
        "local_gguf": {
            "n_ctx": 10,
            "n_gpu_layers": 9999,
            "n_threads": 9999,
            "max_tokens": 1,
        }
    })
    assert s["n_ctx"] == 256
    assert s["n_gpu_layers"] == 200
    assert s["n_threads"] == 128
    assert s["max_tokens"] == 16
