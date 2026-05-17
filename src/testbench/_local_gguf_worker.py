"""Isolated child-process loader for local GGUF models.

Runs ``Llama(...)`` and chat completions in a separate ``python.exe`` so native
crashes (segfault, access violation) do not corrupt the GUI process.

Invocation:

    # Legacy ping test (settings only):
    python -m testbench._local_gguf_worker <settings_json>

    # One-shot job (load model, run job, exit):
    python -m testbench._local_gguf_worker <payload_json>

    # Persistent server (load once, jobs on stdin, one RESULT line per job):
    python -m testbench._local_gguf_worker --serve <settings_json>

``payload_json`` for one-shot::

    {"settings": {...}, "job": {"op": "ping"|"chat", ...}}

Each job on stdin for ``--serve`` is a JSON object with ``op``:

- ``ping`` — connectivity check
- ``chat`` — requires ``messages``, optional ``temperature``, ``max_tokens``
- ``shutdown`` — exit server
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from typing import Any, Dict, List, Optional


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


def _load_model(settings: Dict[str, Any]) -> Any:
    from llama_cpp import Llama  # type: ignore

    model_path = str(settings.get("model_path") or "").strip()
    if not model_path:
        raise ValueError("settings.model_path is empty")
    if not os.path.isfile(model_path):
        raise FileNotFoundError(f"GGUF model file not found: {model_path}")

    return Llama(
        model_path=model_path,
        n_ctx=int(settings.get("n_ctx", 4096)),
        n_threads=int(settings.get("n_threads", 4)),
        n_gpu_layers=int(settings.get("n_gpu_layers", 0)),
        n_batch=int(settings.get("n_batch", 256)),
        chat_format=str(settings.get("chat_format") or "chatml"),
        verbose=bool(settings.get("verbose", False)),
    )


def _run_job(model: Any, job: Dict[str, Any]) -> str:
    op = str(job.get("op") or "ping").strip().lower()
    if op == "ping":
        messages = _PING_MESSAGES
        temperature = 0.0
        max_tokens = 16
    elif op == "chat":
        raw_messages = job.get("messages")
        if not isinstance(raw_messages, list) or not raw_messages:
            raise ValueError("chat job requires non-empty messages list")
        messages = []
        for item in raw_messages:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "user").strip() or "user"
            content = str(item.get("content") or "")
            messages.append({"role": role, "content": content})
        if not messages:
            raise ValueError("chat job has no valid messages")
        temperature = float(job.get("temperature", 0.2))
        max_tokens = int(job.get("max_tokens", 1024))
    else:
        raise ValueError(f"unknown job op: {op!r}")

    resp = model.create_chat_completion(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (resp["choices"][0]["message"]["content"] or "").strip()


def _run_oneshot(settings: Dict[str, Any], job: Dict[str, Any]) -> int:
    try:
        from llama_cpp import Llama  # type: ignore  # noqa: F401
    except Exception as e:
        _emit({"ok": False, "error": f"llama-cpp-python import failed: {e}", "stage": "import"})
        return 2

    try:
        model = _load_model(settings)
    except BaseException as e:
        _emit({
            "ok": False,
            "error": f"Llama load failed: {type(e).__name__}: {e}",
            "stage": "load",
            "trace": traceback.format_exc(),
        })
        return 3

    try:
        text = _run_job(model, job)
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


def _run_serve(settings: Dict[str, Any]) -> int:
    try:
        from llama_cpp import Llama  # type: ignore  # noqa: F401
    except Exception as e:
        _emit({"ok": False, "error": f"llama-cpp-python import failed: {e}", "stage": "import"})
        return 2

    try:
        model = _load_model(settings)
    except BaseException as e:
        _emit({
            "ok": False,
            "error": f"Llama load failed: {type(e).__name__}: {e}",
            "stage": "load",
            "trace": traceback.format_exc(),
        })
        return 3

    _emit({"ok": True, "response": "", "ready": True})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
        except json.JSONDecodeError as e:
            _emit({"ok": False, "error": f"invalid job json: {e}", "stage": "job"})
            continue
        if not isinstance(job, dict):
            _emit({"ok": False, "error": "job must be a JSON object", "stage": "job"})
            continue
        if str(job.get("op") or "").strip().lower() == "shutdown":
            _emit({"ok": True, "response": ""})
            return 0
        try:
            text = _run_job(model, job)
            _emit({"ok": True, "response": text})
        except BaseException as e:
            _emit({
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "stage": "chat",
                "trace": traceback.format_exc(),
            })
    return 0


def _parse_argv() -> tuple[Dict[str, Any], Dict[str, Any], bool]:
    """Return ``(settings, job, serve_mode)``."""
    if len(sys.argv) == 3 and sys.argv[1] == "--serve":
        settings = json.loads(sys.argv[2])
        return settings, {"op": "ping"}, True

    if len(sys.argv) != 2:
        raise ValueError(
            "usage: python -m testbench._local_gguf_worker <payload_json> "
            "or python -m testbench._local_gguf_worker --serve <settings_json>"
        )

    raw = json.loads(sys.argv[1])
    if not isinstance(raw, dict):
        raise ValueError("payload must be a JSON object")

    if "settings" in raw:
        settings = raw.get("settings")
        if not isinstance(settings, dict):
            raise ValueError("payload.settings must be an object")
        job = raw.get("job")
        if not isinstance(job, dict):
            job = {"op": "ping"}
        return settings, job, False

    # Legacy: argv[1] is settings only → ping one-shot.
    return raw, {"op": "ping"}, False


def main() -> int:
    try:
        settings, job, serve_mode = _parse_argv()
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        _emit({"ok": False, "error": str(e)})
        return 2

    if serve_mode:
        return _run_serve(settings)
    return _run_oneshot(settings, job)


if __name__ == "__main__":
    raise SystemExit(main())
