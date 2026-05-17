"""Unit tests for provider resolution, endpoint normalization, and local-GGUF settings."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from testbench.llm_chat import (
    PROVIDER_AZURE,
    PROVIDER_LOCAL_GGUF,
    PROVIDER_OPENAI,
    _ensure_local_gguf_n_ctx,
    _local_gguf_settings,
    _normalize_azure_endpoint,
    _normalize_llm_json_text,
    _parse_plan_response,
    _resolve_provider,
    _safe_ascii_preview,
    _salvage_command_lines,
    _use_local_gguf_subprocess,
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


def test_safe_ascii_preview_strips_non_ascii():
    assert _safe_ascii_preview("OK") == "OK"
    assert _safe_ascii_preview("OK 👋") == "OK ?"


def test_normalize_llm_json_text_strips_arbitrary_fence_tags():
    """Small local models often use ``tool_code`` / ``python`` instead of ``json``."""
    payload = '{"commands": ["bc.osc.run"], "analysis": ""}'
    for tag in ("", "json", "tool_code", "python", "bash"):
        wrapped = f"```{tag}\n{payload}\n```"
        assert _normalize_llm_json_text(wrapped) == payload


def test_salvage_command_lines_recovers_fenced_commands():
    """Gemma 2 sometimes returns a tool_code fence with a bare command line."""
    raw = "```tool_code\nosc.get_trace 1 1024\n```"
    cmds = _salvage_command_lines(raw)
    assert cmds == ["osc.get_trace 1 1024"]


def test_salvage_command_lines_handles_multi_line_block():
    raw = (
        "```python\n"
        "bc.osc.connect\n"
        "bc.osc.set_channel 1 enable\n"
        "bc.osc.measure 1\n"
        "```"
    )
    assert _salvage_command_lines(raw) == [
        "bc.osc.connect",
        "bc.osc.set_channel 1 enable",
        "bc.osc.measure 1",
    ]


def test_salvage_command_lines_rejects_prose():
    """Free-text answers must not be misinterpreted as commands."""
    assert _salvage_command_lines("I will read channel 1 of the oscilloscope.") == []
    assert _salvage_command_lines("```\nThis is an explanation.\n```") == []


def test_parse_plan_response_falls_back_to_salvaged_commands():
    """When the model emits a fenced command list, _parse_plan_response should recover it."""
    cmds, hint = _parse_plan_response("```tool_code\nosc.get_trace 1 1024\n```")
    assert cmds == ["osc.get_trace 1 1024"]
    assert "recovered" in hint.lower()


def test_local_gguf_settings_zero_means_auto_default():
    """0 in the GUI spinboxes means 'auto/default', not literally one thread."""
    defaults = _local_gguf_settings({})
    s = _local_gguf_settings({
        "local_gguf": {
            "n_threads": 0,
            "n_ctx": 0,
            "n_batch": 0,
            "max_tokens": 0,
        }
    })
    assert s["n_threads"] == defaults["n_threads"]
    assert s["n_ctx"] == defaults["n_ctx"]
    assert s["max_tokens"] == defaults["max_tokens"]
    assert s["n_threads"] >= 1
    assert s["n_gpu_layers"] == 0


def test_ensure_local_gguf_n_ctx_bumps_when_prompt_too_large():
    settings = {"n_ctx": 2048, "model_path": "/x/m.gguf"}
    messages = [{"role": "user", "content": "x" * 12000}]
    out = _ensure_local_gguf_n_ctx(settings, messages, max_tokens=512)
    assert out["n_ctx"] > 2048


def test_use_local_gguf_subprocess_default_on():
    assert _use_local_gguf_subprocess() is True


def test_use_local_gguf_subprocess_inprocess_env(monkeypatch):
    monkeypatch.setenv("TESTBENCH_LOCAL_GGUF_INPROCESS", "1")
    assert _use_local_gguf_subprocess() is False
