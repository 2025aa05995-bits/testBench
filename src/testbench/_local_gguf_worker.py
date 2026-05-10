"""Isolated child-process loader for local GGUF models.

Runs ``Llama(...)`` and one chat completion in its own ``python.exe``. Any
native crash (segfault, access violation, std::bad_alloc) terminates only
this child, leaving the parent GUI process intact. The parent reads result
or error from a single line of JSON on stdout (``RESULT:{...}``).

Invocation:

    python -m testbench._local_gguf_worker <settings_json>

where ``<settings_json>`` is a JSON object with at minimum ``model_path`` and
the same keys ``_local_gguf_settings`` returns.
"""
from __future__ import annotations

import json
import os
import sys
import traceback


_PING_MESSAGES = [
    {
        "role": "system",
        "content": (
            "You are a connectivity check. Reply with exactly the two ASCII "
            "letters OK and nothing else: no punctuation, no markdown, no "
            "line breaks, no emoji."
        ),
    },
    {"role": "user", "content": "Ping."},
]


def _emit(payload: dict) -> None:
    sys.stdout.write("RESULT:" + json.dumps(payload) + "\n")
    sys.stdout.flush()


def main() -> int:
    if len(sys.argv) != 2:
        _emit({"ok": False, "error": "usage: python -m testbench._local_gguf_worker <settings_json>"})
        return 2
    try:
        settings = json.loads(sys.argv[1])
    except (json.JSONDecodeError, TypeError) as e:
        _emit({"ok": False, "error": f"invalid settings json: {e}"})
        return 2

    model_path = str(settings.get("model_path") or "").strip()
    if not model_path:
        _emit({"ok": False, "error": "settings.model_path is empty"})
        return 2
    if not os.path.isfile(model_path):
        _emit({"ok": False, "error": f"GGUF model file not found: {model_path}"})
        return 2

    try:
        from llama_cpp import Llama  # type: ignore
    except Exception as e:
        _emit({"ok": False, "error": f"llama-cpp-python import failed: {e}"})
        return 2

    try:
        model = Llama(
            model_path=model_path,
            n_ctx=int(settings.get("n_ctx", 2048)),
            n_threads=int(settings.get("n_threads", 4)),
            n_gpu_layers=int(settings.get("n_gpu_layers", 0)),
            n_batch=int(settings.get("n_batch", 128)),
            chat_format=str(settings.get("chat_format") or "chatml"),
            verbose=False,
        )
    except BaseException as e:
        _emit({
            "ok": False,
            "error": f"Llama load failed: {type(e).__name__}: {e}",
            "stage": "load",
            "trace": traceback.format_exc(),
        })
        return 3

    try:
        resp = model.create_chat_completion(
            messages=_PING_MESSAGES,
            temperature=0.0,
            max_tokens=16,
        )
        text = (resp["choices"][0]["message"]["content"] or "").strip()
    except BaseException as e:
        _emit({
            "ok": False,
            "error": f"Llama chat failed: {type(e).__name__}: {e}",
            "stage": "chat",
            "trace": traceback.format_exc(),
        })
        return 4

    _emit({"ok": True, "response": text})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
