"""LLM-backed natural language → TestBench command plans (multi-provider)."""

import atexit
import json
import os
import re
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from testbench.llm_automation_loop import (
    build_plan_user_content,
    build_repair_user_content,
    repair_system_prompt,
    trim_conversation_turns,
)
from testbench.llm_plan_schema import (
    finalize_plan,
    plan_schema_prompt_section,
    structured_plan_from_payload,
)
from testbench.local_gguf_models import (
    apply_gemma3_load_defaults,
    gemma3_runtime_warning,
    is_gemma3_model_path,
    resolve_local_gguf_chat_format,
)
from testbench.rag import _summarize_results_for_query, retrieve_for_prompt

# Config keys
PROVIDER_AZURE = "azure_openai"
PROVIDER_OPENAI = "openai"
PROVIDER_LOCAL_GGUF = "local_gguf"

# Process-wide cache for the loaded llama.cpp model (heavy to construct).
_LOCAL_GGUF_LOCK: Any = None
_LOCAL_GGUF_CACHE: Dict[str, Any] = {}

# Set to True after the first native in-process llama.cpp load failure.
_LOCAL_GGUF_PRIOR_CRASH: bool = False

# Persistent isolated worker (load once per settings key). Chat uses this by
# default so native crashes never corrupt the GUI process.
_LOCAL_GGUF_SUBPROCESS_CLIENT: Any = None


def _env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise RuntimeError(f"Missing environment variable: {name}")
    return v


def build_allowed_commands_text(registry: Any) -> str:
    """
    Build a compact allow-list for the LLM prompt from CommandRegistry.get_all_commands().
    Format: "<category>.<action> — <description>" one per line.
    """
    out: List[str] = []
    all_cmds = registry.get_all_commands() if registry is not None else {}
    if isinstance(all_cmds, dict):
        for category in sorted(all_cmds.keys()):
            actions = all_cmds.get(category, {})
            if not isinstance(actions, dict):
                continue
            for action in sorted(actions.keys()):
                desc = actions.get(action, "")
                desc = str(desc).strip() if desc is not None else ""
                suffix = f" — {desc}" if desc else ""
                out.append(f"{category}.{action}{suffix}")
    return "\n".join(out)


def _parse_timeout_seconds(*sources: Dict[str, Any]) -> float:
    """First non-empty timeout_seconds among dicts, then env OPENAI_TIMEOUT_SECONDS / AZURE_OPENAI_TIMEOUT_SECONDS, default 60."""
    raw: Any = None
    for d in sources:
        if not isinstance(d, dict):
            continue
        v = d.get("timeout_seconds")
        if v is not None and not (isinstance(v, str) and not str(v).strip()):
            raw = v
            break
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        raw = os.environ.get("OPENAI_TIMEOUT_SECONDS") or os.environ.get("AZURE_OPENAI_TIMEOUT_SECONDS", "60")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        v = 60.0
    return max(5.0, min(600.0, v))


def _is_timeout_error(exc: BaseException) -> bool:
    n = type(exc).__name__
    if n == "APITimeoutError":
        return True
    if n == "TimeoutError":
        return True
    mod = getattr(type(exc), "__module__", "")
    if "httpx" in mod and "Timeout" in n:
        return True
    return False


def _normalize_azure_endpoint(url: str) -> str:
    """Reduce an Azure OpenAI endpoint URL to ``scheme://host[:port]``.

    The SDK's ``azure_endpoint`` argument expects the resource base only.
    Users frequently paste the full request URL from the Foundry/AI Studio
    portal (``…/openai/deployments/<dep>/chat/completions?api-version=…``);
    we strip path and query so the request URL is always well-formed.
    """
    s = (url or "").strip()
    if not s:
        return s
    try:
        from urllib.parse import urlparse
    except ImportError:  # pragma: no cover
        return s.rstrip("/")
    p = urlparse(s)
    if not p.scheme or not p.netloc:
        return s.rstrip("/")
    return f"{p.scheme}://{p.netloc}"


def _normalize_llm_json_text(content: str) -> str:
    """Strip markdown fences and isolate a JSON object if one is present.

    Accepts any language tag inside the fence (e.g. ``json``, ``tool_code``,
    ``python``, ``bash``) — small local models are inconsistent about this.
    """
    s = (content or "").strip()
    if not s:
        return s
    fence = re.search(r"```([a-zA-Z0-9_+-]*)\s*\r?\n?([\s\S]*?)\r?\n?```", s)
    if fence:
        s = fence.group(2).strip()
    if s.startswith("{") and s.endswith("}"):
        return s
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        return s[start : end + 1].strip()
    return s


_COMMAND_LINE_RE = re.compile(r"^[A-Za-z_][\w.]*(?:\s+\S.*)?$")
_SALVAGE_LINE_RE = re.compile(
    r"^(?:bc\.|bench\.)?[A-Za-z_][\w.]*(?:\([^)]*\))?(?:\s+[-\d.eE+]+)?$"
)


def _normalize_salvaged_line(raw_line: str) -> Optional[str]:
    """Turn ``ps.off()`` / ``ps.off`` into ``bc.ps.off`` when possible."""
    line = (raw_line or "").strip().rstrip(";")
    if not line or line.startswith("#") or line.startswith("//"):
        return None
    if line.endswith(":") or line.endswith("."):
        return None
    line = re.sub(r"\(\s*\)", "", line)
    low = line.lower()
    if low.startswith(("bc.", "bench.", "delay ", "help", "plot ", "assert ", "limit ")):
        pass
    elif re.match(r"^[a-z_]+\.[a-z_0-9]+", line, re.IGNORECASE):
        line = "bc." + line
    if _COMMAND_LINE_RE.match(line):
        return line
    if _SALVAGE_LINE_RE.match(line):
        return line
    return None


def _salvage_command_lines(content: str) -> List[str]:
    """Best-effort recovery when the model emits plain command lines, not JSON.

    Strips a single surrounding code fence (any language tag) and returns
    non-empty, non-comment lines that look like ``identifier[.identifier]
    [args...]``. Returns an empty list when the content does not look like
    a command list (e.g. it's prose).
    """
    s = (content or "").strip()
    if not s:
        return []
    fence = re.search(r"```([a-zA-Z0-9_+-]*)\s*\r?\n?([\s\S]*?)\r?\n?```", s)
    if fence:
        s = fence.group(2).strip()
    cmds: List[str] = []
    for raw_line in s.splitlines():
        line = _normalize_salvaged_line(raw_line)
        if line:
            cmds.append(line)
        if len(cmds) >= 32:
            break
    return cmds


def _system_prompt() -> str:
    return (
        "You convert user requests into TestBench commands.\n"
        "Return ONLY raw JSON (no markdown, no code fences, no ```json or "
        "```tool_code blocks, no text before or after the object) with keys:\n"
        '- "commands": array of strings\n'
        '- "analysis": string\n'
        "\n"
        + plan_schema_prompt_section()
        + "\nAllowed command forms:\n"
        "- bench.<category>.<action> [args...]\n"
        "- bc.<category>.<action> [args...]\n"
        '- "delay <seconds>"\n'
        '- "help" or "help <category>"\n'
        '- plot <bench/bc command>  (or: plot "Label" <bench/bc command>)\n'
        '- quoted heading: "Title"\n'
        '- assert <bench_command> <expected> <tolerance>\n'
        '- limit <bench_command> <min> <max>  (or min=/max=/field= form)\n'
        "\n"
        "Rules:\n"
        "- Do NOT invent categories/actions; use only items in ALLOWED.\n"
        "- Prefer bc.* unless the user explicitly asks for bench.*.\n"
        "- Every instrument command MUST be bc.<category>.<action> or bench.<category>.<action> "
        "(e.g. bc.osc.run). Never emit bare category.action like osc.run.\n"
        "- Keep commands minimal and safe; avoid raw SCPI unless user explicitly asks.\n"
        "- The commands array must contain ONLY executable lines (bc.*, bench.*, delay, "
        "assert, limit, plot, help). Do NOT put section titles like Power Cycle in "
        'commands — use a quoted heading line "Power Cycle" if you need a label.\n'
        "- If a CONTEXT block is present, treat it as internal reference material "
        "(SOPs, datasheets, lab notes). Use it to choose parameters and order, but "
        "do NOT mention or quote it in the analysis text.\n"
    )


def _system_prompt_local() -> str:
    """Shorter plan prompt for small local models (Gemma 1B–4B, etc.)."""
    return (
        "You convert lab requests into TestBench command lines.\n"
        "Output ONLY one JSON object. No markdown fences. No Python. No explanations outside JSON.\n"
        'Required keys: "commands" (array of strings), "analysis" (short string).\n'
        "\n"
        "Example for power-cycling a power supply:\n"
        '{"commands": ["bc.ps.off", "delay 1", "bc.ps.on"], "analysis": "Power-cycle the supply"}\n'
        "\n"
        "Rules:\n"
        "- Use ONLY commands listed under ALLOWED in the user message.\n"
        "- Format: bc.<category>.<action> [args] or bench.<category>.<action> [args].\n"
        "- Also allowed: delay N, help, plot ..., assert ..., limit ...\n"
        "- Never invent actions. Never output Python, shell scripts, or tutorials.\n"
        "- commands must be executable only — not bare titles like Power Cycle "
        '(use "Power Cycle" as a quoted heading if needed).\n'
    )


def _use_local_compact_prompt(cfg: Dict[str, Any]) -> bool:
    """Trim allow-list and use strict JSON prompt for local GGUF (default on)."""
    llm = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    if not isinstance(llm, dict):
        return _resolve_provider(cfg) == PROVIDER_LOCAL_GGUF
    v = llm.get("local_compact_prompt")
    if v is None:
        return _resolve_provider(cfg) == PROVIDER_LOCAL_GGUF
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() not in {"false", "0", "no", "off"}
    return bool(v)


_CATEGORY_HINTS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("ps", ("power supply", "power cycle", "psu", "voltage", "current", "bc.ps", "bench.ps")),
    ("osc", ("oscilloscope", "scope", "trace", "waveform", "bc.osc")),
    ("sg", ("signal generator", "bc.sg")),
    ("sa", ("spectrum", "bc.sa")),
    ("mm", ("multimeter", "dmm", "bc.mm")),
    ("fg", ("function generator", "bc.fg")),
    ("na", ("network analyzer", "vna", "bc.na")),
    ("el", ("electronic load", "load", "bc.el")),
    ("smu", ("smu", "source measure", "bc.smu")),
    ("tc", ("chamber", "temperature", "bc.tc")),
    ("pm", ("power meter", "bc.pm")),
    ("san", ("signal analyzer", "bc.san")),
    ("fc", ("frequency counter", "bc.fc")),
    ("config", ("config", "visa", "bind", "connect", "bench.config")),
    ("plot", ("plot",)),
    ("arb", ("arb", "waveform csv", "bc.fg.load_arb")),
)


def filter_allowed_commands_text(
    allowed: str, user_text: str, *, max_lines: int = 72
) -> str:
    """Return a smaller allow-list matched to keywords in the user request."""
    lines = [ln for ln in (allowed or "").splitlines() if ln.strip()]
    if not lines:
        return allowed
    ut = (user_text or "").lower()
    categories: set[str] = set()
    for cat, hints in _CATEGORY_HINTS:
        if any(h in ut for h in hints):
            categories.add(cat)
    if not categories:
        return "\n".join(lines[:max_lines])
    picked: List[str] = []
    for ln in lines:
        head = ln.split(".", 1)[0].strip().lower()
        if head in categories:
            picked.append(ln)
    if not picked:
        return "\n".join(lines[:max_lines])
    if len(picked) > max_lines:
        picked = picked[:max_lines]
    return "\n".join(picked)


def _plan_system_prompt(cfg: Dict[str, Any]) -> str:
    if _use_local_compact_prompt(cfg):
        return _system_prompt_local()
    return _system_prompt()


def _plan_include_checks(cfg: Optional[Dict[str, Any]]) -> bool:
    llm = (cfg or {}).get("llm") if isinstance(cfg, dict) else {}
    if not isinstance(llm, dict):
        return True
    v = llm.get("plan_include_checks", True)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() not in {"false", "0", "no", "off"}
    return bool(v)


def _parse_plan_response(content: str, cfg: Optional[Dict[str, Any]] = None) -> Tuple[List[str], str]:
    raw = (content or "").strip()
    if not raw:
        raise RuntimeError("Model returned empty response.")
    normalized = _normalize_llm_json_text(raw)
    if not normalized:
        raise RuntimeError("Model returned empty response after stripping markdown.")
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError as e:
        salvaged = _salvage_command_lines(raw)
        if salvaged:
            return salvaged, (
                "(recovered plain command list from non-JSON model response)"
            )
        hint = ""
        low = raw.lower()
        if "```python" in low or "def " in raw[:200]:
            hint = (
                "\n\nThe model returned Python instead of JSON. This is common with "
                "small local models (e.g. Gemma 3 1B). Try a larger instruct GGUF "
                "(7B+), set local_gguf.temperature to 0.0, or ensure llm.local_compact_prompt "
                "is true (default for local GGUF).\n"
            )
        raise RuntimeError(
            "Model did not return valid JSON. Update the prompt or reduce temperature."
            f"{hint}\nRaw content:\n{raw}"
        ) from e

    if isinstance(payload, list):
        cmds = [str(c).strip() for c in payload if str(c).strip()]
        if cmds:
            return cmds, "(recovered command list from JSON array response)"
        raise RuntimeError(
            "Model returned a JSON array with no commands.\n"
            f"Raw content:\n{raw}"
        )
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Model returned unexpected JSON type {type(payload).__name__}.\n"
            f"Raw content:\n{raw}"
        )

    plan = structured_plan_from_payload(payload)
    return finalize_plan(plan, include_checks=_plan_include_checks(cfg))


def _plan_context_kwargs(
    user_text: str,
    registry: Any,
    cfg: Dict[str, Any],
    *,
    conversation_turns: Optional[List[Dict[str, Any]]] = None,
    last_results: Optional[List[Dict[str, Any]]] = None,
    last_commands: Optional[List[str]] = None,
) -> Tuple[str, str]:
    """Return ``(allowed_text, user_content)`` for plan/repair prompts."""
    allowed = build_allowed_commands_text(registry)
    if _use_local_compact_prompt(cfg):
        allowed = filter_allowed_commands_text(allowed, user_text or "")
    rag_block, _ = retrieve_for_prompt(user_text or "", cfg)
    if _use_local_compact_prompt(cfg) and rag_block:
        cap = 1200
        if len(rag_block) > cap:
            rag_block = rag_block[: cap - 3] + "..."
    llm = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    max_hist = 8
    if isinstance(llm, dict):
        from testbench.llm_automation_loop import AutomationLoopConfig

        max_hist = AutomationLoopConfig.from_config(cfg).multi_turn_history
    turns = trim_conversation_turns(conversation_turns or [], max_hist)
    user_content = build_plan_user_content(
        user_text,
        allowed,
        rag_block,
        conversation_turns=turns,
        last_results=last_results,
        last_commands=last_commands,
    )
    return allowed, user_content


def _azure_chat_to_plan(
    user_text: str,
    registry: Any,
    cfg: Dict[str, Any],
    timeout_sec: float,
    *,
    conversation_turns: Optional[List[Dict[str, Any]]] = None,
    last_results: Optional[List[Dict[str, Any]]] = None,
    last_commands: Optional[List[str]] = None,
) -> Tuple[List[str], str]:
    try:
        from openai import AzureOpenAI  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "OpenAI SDK not available. Install dependency: pip install openai"
        ) from e

    aoai = cfg.get("azure_openai", {}) if isinstance(cfg, dict) else {}
    if not isinstance(aoai, dict):
        aoai = {}

    endpoint = (str(aoai.get("endpoint", "") or "").strip()) or os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
    api_key = (str(aoai.get("api_key", "") or "").strip()) or os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
    deployment = (str(aoai.get("deployment", "") or "").strip()) or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "").strip()
    api_version = (
        (str(aoai.get("api_version", "") or "").strip())
        or os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview").strip()
    )
    if not api_version:
        api_version = "2024-02-15-preview"

    if not endpoint:
        endpoint = _env("AZURE_OPENAI_ENDPOINT")
    if not api_key:
        api_key = _env("AZURE_OPENAI_API_KEY")
    if not deployment:
        deployment = _env("AZURE_OPENAI_DEPLOYMENT")

    _, user_content = _plan_context_kwargs(
        user_text,
        registry,
        cfg,
        conversation_turns=conversation_turns,
        last_results=last_results,
        last_commands=last_commands,
    )
    client = AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=_normalize_azure_endpoint(endpoint),
        timeout=timeout_sec,
    )

    try:
        resp = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            timeout=timeout_sec,
        )
    except Exception as e:
        if _is_timeout_error(e):
            raise RuntimeError(
                f"Azure OpenAI did not respond within {int(timeout_sec)} second(s). "
                "Increase timeout in LLM settings or check network and endpoint."
            ) from e
        raise

    content = (resp.choices[0].message.content or "").strip()
    return _parse_plan_response(content, cfg)


def _openai_direct_chat_to_plan(
    user_text: str,
    registry: Any,
    cfg: Dict[str, Any],
    timeout_sec: float,
    *,
    conversation_turns: Optional[List[Dict[str, Any]]] = None,
    last_results: Optional[List[Dict[str, Any]]] = None,
    last_commands: Optional[List[str]] = None,
) -> Tuple[List[str], str]:
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "OpenAI SDK not available. Install dependency: pip install openai"
        ) from e

    oa = cfg.get("openai_api", {}) if isinstance(cfg, dict) else {}
    if not isinstance(oa, dict):
        oa = {}

    api_key = (str(oa.get("api_key", "") or "").strip()) or os.environ.get("OPENAI_API_KEY", "").strip()
    model = (str(oa.get("model", "") or "").strip()) or os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
    base_url = (str(oa.get("base_url", "") or "").strip()) or os.environ.get("OPENAI_BASE_URL", "").strip()

    if not api_key:
        api_key = _env("OPENAI_API_KEY")
    if not model:
        model = "gpt-4o-mini"

    _, user_content = _plan_context_kwargs(
        user_text,
        registry,
        cfg,
        conversation_turns=conversation_turns,
        last_results=last_results,
        last_commands=last_commands,
    )
    kwargs: Dict[str, Any] = {"api_key": api_key, "timeout": timeout_sec}
    if base_url:
        kwargs["base_url"] = base_url.rstrip("/")

    client = OpenAI(**kwargs)

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            timeout=timeout_sec,
        )
    except Exception as e:
        if _is_timeout_error(e):
            raise RuntimeError(
                f"OpenAI API did not respond within {int(timeout_sec)} second(s). "
                "Increase timeout in LLM settings or check network."
            ) from e
        raise

    content = (resp.choices[0].message.content or "").strip()
    return _parse_plan_response(content, cfg)


_PROVIDER_ALIASES = {
    "azure": PROVIDER_AZURE,
    "azure_openai": PROVIDER_AZURE,
    "aoai": PROVIDER_AZURE,
    "openai": PROVIDER_OPENAI,
    "openai_api": PROVIDER_OPENAI,
    "local": PROVIDER_LOCAL_GGUF,
    "local_gguf": PROVIDER_LOCAL_GGUF,
    "gguf": PROVIDER_LOCAL_GGUF,
    "llama_cpp": PROVIDER_LOCAL_GGUF,
    "llama-cpp": PROVIDER_LOCAL_GGUF,
}


def _resolve_provider(cfg: Dict[str, Any]) -> str:
    llm = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    p = str((llm or {}).get("provider", "") or "").strip().lower()
    return _PROVIDER_ALIASES.get(p, PROVIDER_AZURE)


def _local_gguf_settings(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve ``local_gguf`` config with env fallbacks and safe defaults."""
    raw = cfg.get("local_gguf") if isinstance(cfg, dict) else None
    if not isinstance(raw, dict):
        raw = {}
    model_path = str(raw.get("model_path", "") or "").strip() or os.environ.get("LOCAL_GGUF_MODEL_PATH", "").strip()

    def _int(key: str, default: int, lo: int, hi: int, *, zero_means_default: bool = False) -> int:
        v = raw.get(key)
        try:
            n = int(v) if v is not None and not (isinstance(v, str) and not v.strip()) else default
        except (TypeError, ValueError):
            n = default
        if zero_means_default and n == 0:
            n = default
        return max(lo, min(hi, n))

    def _float(key: str, default: float, lo: float, hi: float) -> float:
        v = raw.get(key)
        try:
            n = float(v) if v is not None and not (isinstance(v, str) and not str(v).strip()) else default
        except (TypeError, ValueError):
            n = default
        return max(lo, min(hi, n))

    explicit_chat_format = str(raw.get("chat_format", "") or "").strip().lower()
    chat_format = resolve_local_gguf_chat_format(model_path, explicit_chat_format)

    resolved = {
        "model_path": model_path,
        "n_ctx": _int("n_ctx", 4096, 256, 131072, zero_means_default=True),
        "n_threads": _int(
            "n_threads",
            max(1, (os.cpu_count() or 4) // 2),
            1,
            128,
            zero_means_default=True,
        ),
        "n_gpu_layers": _int("n_gpu_layers", 0, -1, 200),
        "n_batch": _int("n_batch", 256, 32, 4096, zero_means_default=True),
        "max_tokens": _int("max_tokens", 1024, 16, 32768, zero_means_default=True),
        "temperature": _float("temperature", 0.1, 0.0, 2.0),
        "chat_format": chat_format,
        "verbose": bool(raw.get("verbose", False)),
    }
    return apply_gemma3_load_defaults(resolved)


def _load_local_gguf_model(settings: Dict[str, Any]) -> Any:
    """Lazily load and cache a ``llama_cpp.Llama`` instance keyed by load args."""
    global _LOCAL_GGUF_LOCK, _LOCAL_GGUF_PRIOR_CRASH
    try:
        from llama_cpp import Llama  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "llama-cpp-python is not installed. Install with:\n"
            "  pip install llama-cpp-python\n"
            "(GPU builds: see https://github.com/abetlen/llama-cpp-python#installation)"
        ) from e

    model_path = settings.get("model_path") or ""
    if not model_path:
        raise RuntimeError(
            "No GGUF model path configured. Set local_gguf.model_path in the bench "
            "JSON or LOCAL_GGUF_MODEL_PATH in the environment."
        )
    if not os.path.isfile(model_path):
        raise RuntimeError(f"GGUF model file not found: {model_path}")

    if _LOCAL_GGUF_PRIOR_CRASH:
        raise RuntimeError(
            "Local GGUF model load is disabled in this process because a previous "
            "load crashed in native code (access violation).\n\n"
            "RESTART the chat application before retrying — the C++ heap is "
            "corrupted after a crash and any further Llama(...) call in the same "
            "process will keep failing in the same place."
        )

    _preflight_local_gguf_memory(model_path, settings)

    if _LOCAL_GGUF_LOCK is None:
        import threading
        _LOCAL_GGUF_LOCK = threading.Lock()

    key_parts = (
        os.path.abspath(model_path),
        int(settings.get("n_ctx", 0)),
        int(settings.get("n_threads", 0)),
        int(settings.get("n_gpu_layers", 0)),
        int(settings.get("n_batch", 0)),
        str(settings.get("chat_format") or ""),
    )
    key = "|".join(str(x) for x in key_parts)
    with _LOCAL_GGUF_LOCK:
        cached = _LOCAL_GGUF_CACHE.get(key)
        if cached is not None:
            return cached
        try:
            from testbench.local_gguf_models import build_llama_kwargs

            if is_gemma3_model_path(model_path):
                warn = gemma3_runtime_warning()
                if warn:
                    raise RuntimeError(warn)
            model = Llama(**build_llama_kwargs(settings))
        except Exception as e:
            msg = str(e) or type(e).__name__
            if "access violation" in msg.lower() or "0x0000000000000000" in msg:
                _LOCAL_GGUF_PRIOR_CRASH = True
            raise RuntimeError(_format_local_gguf_load_error(model_path, e)) from e
        _LOCAL_GGUF_CACHE[key] = model
        return model


def _query_free_ram_bytes() -> Optional[int]:
    """Return current free physical RAM in bytes, or None if unknown.

    Uses Windows ``GlobalMemoryStatusEx`` and falls back to ``/proc/meminfo``
    on Linux. Best-effort only; never raises.
    """
    try:
        import ctypes

        if hasattr(ctypes, "windll"):
            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return int(stat.ullAvailPhys)
    except Exception:
        pass
    try:
        with open("/proc/meminfo", "r", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return None


def _preflight_local_gguf_memory(model_path: str, settings: Dict[str, Any]) -> None:
    """Fail fast with a friendly message when free RAM is clearly insufficient.

    Estimates needed memory as ``file_size + KV cache rough + 0.4 GB scratch``.
    A KV cache rough is ``n_ctx * 0.0001`` GB (overshoots small models slightly,
    undershoots very wide models — close enough for an OOM warning). Skips
    silently when free RAM cannot be determined.
    """
    free = _query_free_ram_bytes()
    if free is None:
        return
    try:
        file_size = os.path.getsize(model_path)
    except OSError:
        return
    n_ctx = int(settings.get("n_ctx", 4096) or 4096)
    kv_rough = int(n_ctx * 100_000)
    scratch = 400 * 1024 * 1024
    needed = file_size + kv_rough + scratch
    if free + (256 * 1024 * 1024) < needed:
        free_gb = free / (1024**3)
        need_gb = needed / (1024**3)
        file_gb = file_size / (1024**3)
        raise RuntimeError(
            "Not enough free RAM to load the GGUF safely.\n"
            f"  - Free physical RAM: {free_gb:.2f} GB\n"
            f"  - Estimated needed:  {need_gb:.2f} GB "
            f"(file {file_gb:.2f} GB + KV cache @ n_ctx={n_ctx} + scratch)\n"
            "Fix one of the following, then retry:\n"
            "  - Lower n_ctx (try 2048), n_batch (128), max_tokens (512) in LLM settings.\n"
            "  - Close other applications to free memory.\n"
            "  - Use a smaller GGUF (e.g. Llama-3.2-1B-Instruct Q4_K_M, ~770 MB).\n"
            "  - Restart the chat application before retrying (a previous crash may "
            "have left memory mapped)."
        )


def _format_local_gguf_load_error(model_path: str, exc: BaseException) -> str:
    """Build a human-friendly hint for common ``Llama(...)`` failures.

    The native llama.cpp loader raises C++ exceptions / NULL-deref access
    violations for two very different reasons:

    1. **Out of memory** — most common on 8 GB Windows machines. The loader
       mmaps the GGUF, fails to commit pages for the model + KV cache, and
       dereferences NULL deep in ggml. Hints below check current free RAM
       against a rough estimate of what the file needs.
    2. **GGUF newer than the runtime** — e.g. Gemma 3 on the bundled
       llama.cpp shipped with ``llama-cpp-python`` 0.3.22.
    """
    msg = str(exc) or type(exc).__name__
    name = os.path.basename(model_path).lower()
    is_access_violation = "access violation" in msg.lower() or "0x0000000000000000" in msg
    extras: List[str] = []
    try:
        import llama_cpp  # type: ignore
        rt_ver = getattr(llama_cpp, "__version__", "?")
    except Exception:
        rt_ver = "?"
    extras.append(f"llama-cpp-python runtime: {rt_ver}")

    free_gb: Optional[float] = None
    file_gb: Optional[float] = None
    try:
        if os.path.isfile(model_path):
            file_gb = os.path.getsize(model_path) / (1024**3)
    except OSError:
        pass
    try:
        import ctypes

        class _MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        if hasattr(ctypes, "windll"):
            stat = _MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                free_gb = stat.ullAvailPhys / (1024**3)
    except Exception:
        pass

    likely_oom = (
        is_access_violation
        and free_gb is not None
        and file_gb is not None
        and free_gb < (file_gb + 0.4)
    )
    plenty_of_ram = (
        is_access_violation
        and free_gb is not None
        and file_gb is not None
        and free_gb > (file_gb + 0.8)
    )

    if is_access_violation:
        extras.append(
            "RESTART the chat application before retrying — after a native "
            "access-violation crash, the C++ heap is corrupted and any further "
            "Llama(...) call in the same process tends to crash in the same place. "
            "This is the single most common cause of 'second test also failed'."
        )

    if likely_oom:
        extras.append(
            f"Out of memory may also apply: free RAM {free_gb:.2f} GB vs model "
            f"file {file_gb:.2f} GB. Lower n_ctx/n_batch/max_tokens or pick a "
            "smaller GGUF (e.g. Qwen2.5-0.5B-Instruct ~470 MB)."
        )
    elif plenty_of_ram:
        extras.append(
            f"OOM is unlikely here: free RAM {free_gb:.2f} GB vs model file "
            f"{file_gb:.2f} GB. The crash is almost certainly leftover state "
            "from a previous load attempt — restart the application."
        )

    if is_gemma3_model_path(model_path):
        warn = gemma3_runtime_warning()
        if warn:
            extras.append(warn)
        extras.append(
            "Gemma 3 uses chat_format=gemma in llama-cpp-python. Set chat_format to "
            "'gemma-3' or 'auto' in LLM settings; use a Q4_K_M / Q5_K_M instruct GGUF."
        )
    elif is_access_violation and not (likely_oom or plenty_of_ram):
        extras.append(
            "If restarting does not help, the GGUF may need a newer llama.cpp "
            "than the installed wheel. Try:  pip install --upgrade --prefer-binary "
            "llama-cpp-python  or pick a different GGUF."
        )
    elif not is_access_violation:
        extras.append(
            "If this looks like a tokenizer or architecture error, upgrade "
            "llama-cpp-python or pick a different GGUF."
        )

    return (
        f"Failed to load GGUF model {model_path!r}: {msg}\n"
        + "\n".join(f"  - {x}" for x in extras)
    )


def _ensure_local_gguf_n_ctx(
    settings: Dict[str, Any],
    messages: List[Dict[str, str]],
    max_tokens: int,
) -> Dict[str, Any]:
    """Raise ``n_ctx`` when the prompt clearly exceeds the configured window."""
    est_prompt = sum(len(str(m.get("content") or "")) for m in messages) // 4 + 64
    need = est_prompt + int(max_tokens) + 128
    have = int(settings.get("n_ctx", 4096) or 4096)
    if need <= have:
        return settings
    bumped = dict(settings)
    bumped["n_ctx"] = min(131072, max(have, need, 4096))
    return bumped


def _use_local_gguf_subprocess() -> bool:
    """True unless TESTBENCH_LOCAL_GGUF_INPROCESS=1 forces in-process load."""
    v = os.environ.get("TESTBENCH_LOCAL_GGUF_INPROCESS", "").strip().lower()
    return v not in {"1", "true", "yes", "on"}


def _local_gguf_worker_env() -> Dict[str, str]:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    py_path = env.get("PYTHONPATH", "")
    if repo_root not in py_path.split(os.pathsep):
        env["PYTHONPATH"] = (repo_root + os.pathsep + py_path) if py_path else repo_root
    return env


def _parse_local_gguf_worker_stdout(stdout: str, stderr: str, returncode: int) -> str:
    parsed: Optional[Dict[str, Any]] = None
    for line in (stdout or "").splitlines():
        if line.startswith("RESULT:"):
            try:
                parsed = json.loads(line[len("RESULT:") :])
            except json.JSONDecodeError:
                parsed = None
    if parsed is None:
        details = (stderr or "").strip().splitlines()[-12:]
        raise RuntimeError(
            "Local GGUF worker did not return a result.\n"
            f"  - Exit code: {returncode}\n"
            "  - Last child output:\n    "
            + "\n    ".join(details or ["(no output)"])
        )
    if not parsed.get("ok"):
        err = str(parsed.get("error") or "unknown error")
        stage = parsed.get("stage") or "?"
        details = (stderr or "").strip().splitlines()[-12:]
        raise RuntimeError(
            f"Local GGUF worker failed at stage {stage!r}: {err}\n"
            "  - Native work ran in an isolated child process; the GUI is unaffected.\n"
            "  - Last child output:\n    "
            + "\n    ".join(details or ["(no output)"])
        )
    return str(parsed.get("response") or "")


class _LocalGgufSubprocessClient:
    """Keeps one ``--serve`` worker alive per resolved settings key."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: Any = None
        self._active_key: Optional[str] = None

    def _make_settings_key(self, settings: Dict[str, Any]) -> str:
        return "|".join(
            str(x)
            for x in (
                os.path.abspath(str(settings.get("model_path") or "")),
                int(settings.get("n_ctx", 0)),
                int(settings.get("n_threads", 0)),
                int(settings.get("n_gpu_layers", 0)),
                int(settings.get("n_batch", 0)),
                str(settings.get("chat_format") or ""),
            )
        )

    def _stop_unlocked(self) -> None:
        proc = self._proc
        self._proc = None
        self._active_key = None
        if proc is None:
            return
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.write(json.dumps({"op": "shutdown"}) + "\n")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _start_unlocked(self, settings: Dict[str, Any]) -> None:
        import subprocess

        cmd = [
            sys.executable,
            "-m",
            "testbench._local_gguf_worker",
            "--serve",
            json.dumps(settings),
        ]
        creation_flags = 0
        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_local_gguf_worker_env(),
            creationflags=creation_flags,
        )
        self._active_key = self._make_settings_key(settings)
        deadline = time.monotonic() + 600.0
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                err = (self._proc.stderr.read() if self._proc.stderr else "") or ""
                raise RuntimeError(
                    "Local GGUF worker exited during startup.\n"
                    + "\n".join(f"  - {ln}" for ln in err.strip().splitlines()[-8:] or ["(no stderr)"])
                )
            line = self._proc.stdout.readline() if self._proc.stdout else ""
            if line.startswith("RESULT:"):
                try:
                    payload = json.loads(line[len("RESULT:") :])
                except json.JSONDecodeError:
                    continue
                if payload.get("ok") and payload.get("ready"):
                    return
                if not payload.get("ok"):
                    raise RuntimeError(
                        f"Local GGUF worker failed to start: {payload.get('error') or payload}"
                    )
        raise RuntimeError("Local GGUF worker startup timed out (600 s).")

    def run_job(self, settings: Dict[str, Any], job: Dict[str, Any], wall_timeout: float) -> str:
        with self._lock:
            key = self._make_settings_key(settings)
            if self._proc is None or self._proc.poll() is not None or key != self._active_key:
                self._stop_unlocked()
                self._start_unlocked(settings)
            assert self._proc is not None and self._proc.stdin is not None
            try:
                self._proc.stdin.write(json.dumps(job) + "\n")
                self._proc.stdin.flush()
            except Exception as e:
                self._stop_unlocked()
                raise RuntimeError(f"Failed to send job to local GGUF worker: {e}") from e

            deadline = time.monotonic() + max(5.0, float(wall_timeout))
            while time.monotonic() < deadline:
                if self._proc.poll() is not None:
                    err = (self._proc.stderr.read() if self._proc.stderr else "") or ""
                    self._stop_unlocked()
                    raise RuntimeError(
                        "Local GGUF worker crashed during inference.\n"
                        "Restart the chat app and retry. If this persists, upgrade "
                        "llama-cpp-python or use a different GGUF.\n"
                        + "\n".join(
                            f"  - {ln}" for ln in err.strip().splitlines()[-8:] or ["(no stderr)"]
                        )
                    )
                line = self._proc.stdout.readline() if self._proc.stdout else ""
                if not line:
                    continue
                if line.startswith("RESULT:"):
                    try:
                        payload = json.loads(line[len("RESULT:") :])
                    except json.JSONDecodeError:
                        continue
                    if not payload.get("ok"):
                        err = str(payload.get("error") or "unknown error")
                        stage = payload.get("stage") or "?"
                        raise RuntimeError(
                            f"Local GGUF worker failed at stage {stage!r}: {err}"
                        )
                    return str(payload.get("response") or "")
            self._stop_unlocked()
            raise RuntimeError(
                f"Local GGUF inference timed out after {int(wall_timeout)} s. "
                "Increase Request timeout in LLM settings or use a smaller model."
            )

    def shutdown(self) -> None:
        with self._lock:
            self._stop_unlocked()


def _local_gguf_subprocess_client() -> _LocalGgufSubprocessClient:
    global _LOCAL_GGUF_SUBPROCESS_CLIENT
    if _LOCAL_GGUF_SUBPROCESS_CLIENT is None:
        _LOCAL_GGUF_SUBPROCESS_CLIENT = _LocalGgufSubprocessClient()
        atexit.register(_LOCAL_GGUF_SUBPROCESS_CLIENT.shutdown)
    return _LOCAL_GGUF_SUBPROCESS_CLIENT


def _local_gguf_run_oneshot(
    settings: Dict[str, Any], job: Dict[str, Any], wall_timeout: float
) -> str:
    import subprocess

    payload = json.dumps({"settings": settings, "job": job})
    cmd = [sys.executable, "-m", "testbench._local_gguf_worker", payload]
    creation_flags = 0
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            cmd,
            input="",
            capture_output=True,
            text=True,
            timeout=wall_timeout,
            env=_local_gguf_worker_env(),
            creationflags=creation_flags,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"Local GGUF worker timed out after {int(wall_timeout)} s. "
            "Increase Request timeout (try 300 s) or pick a smaller GGUF."
        ) from e
    return _parse_local_gguf_worker_stdout(proc.stdout or "", proc.stderr or "", proc.returncode)


def _local_gguf_chat_via_subprocess(
    messages: List[Dict[str, str]],
    settings: Dict[str, Any],
    cfg: Dict[str, Any],
    *,
    temperature: float = 0.2,
    max_tokens: int,
) -> str:
    llm = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    aoai = cfg.get("azure_openai") if isinstance(cfg.get("azure_openai"), dict) else {}
    oa = cfg.get("openai_api") if isinstance(cfg.get("openai_api"), dict) else {}
    wall_timeout = max(90.0, _parse_timeout_seconds(llm or {}, aoai or {}, oa or {}))
    job = {
        "op": "chat",
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }
    return _local_gguf_subprocess_client().run_job(settings, job, wall_timeout)


def _local_gguf_chat(
    messages: List[Dict[str, str]],
    cfg: Dict[str, Any],
    *,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    """Chat-completion via isolated subprocess (default) or in-process fallback."""
    settings = _local_gguf_settings(cfg)
    mt = int(max_tokens if max_tokens is not None else settings.get("max_tokens", 1024))
    temp = float(
        temperature if temperature is not None else settings.get("temperature", 0.1)
    )
    settings = _ensure_local_gguf_n_ctx(settings, messages, mt)
    if _use_local_gguf_subprocess():
        return _local_gguf_chat_via_subprocess(
            messages, settings, cfg, temperature=temp, max_tokens=mt
        )
    model = _load_local_gguf_model(settings)
    try:
        resp = model.create_chat_completion(
            messages=messages,
            temperature=temp,
            max_tokens=mt,
        )
    except Exception as e:
        raise RuntimeError(f"Local GGUF model error: {e}") from e
    try:
        return (resp["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Local GGUF model returned an unexpected response: {resp!r}") from e


def _local_gguf_chat_to_plan(
    user_text: str,
    registry: Any,
    cfg: Dict[str, Any],
    *,
    conversation_turns: Optional[List[Dict[str, Any]]] = None,
    last_results: Optional[List[Dict[str, Any]]] = None,
    last_commands: Optional[List[str]] = None,
) -> Tuple[List[str], str]:
    _, user_content = _plan_context_kwargs(
        user_text,
        registry,
        cfg,
        conversation_turns=conversation_turns,
        last_results=last_results,
        last_commands=last_commands,
    )
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": _plan_system_prompt(cfg)},
        {"role": "user", "content": user_content},
    ]
    content = _local_gguf_chat(messages, cfg)
    return _parse_plan_response(content, cfg)


def _ping_messages() -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a connectivity check. Reply with exactly the two ASCII letters OK "
                "and nothing else: no punctuation, no markdown, no line breaks, no emoji."
            ),
        },
        {"role": "user", "content": "Ping."},
    ]


def _safe_ascii_preview(s: str, limit: int = 160) -> str:
    """Plain-text preview safe for Windows QMessageBox / Tk dialogs (ASCII-only)."""
    t = (s or "").replace("\r\n", "\n").strip()
    if len(t) > limit:
        t = t[: limit - 3] + "..."
    out: List[str] = []
    for ch in t:
        o = ord(ch)
        if o < 32 and ch not in "\n\t":
            out.append("?")
        elif o <= 127:
            out.append(ch)
        else:
            out.append("?")
    return "".join(out)


def _is_running_under_debugger() -> bool:
    """Heuristic: are we running under debugpy / VS Code / Cursor debugger?

    Native llama.cpp loaders frequently produce NULL-deref access violations
    when ``sys.settrace`` is hooked by debugpy in worker threads, so we use
    this to (a) warn users and (b) force subprocess isolation in tests.
    """
    if "debugpy" in sys.modules:
        return True
    for name in ("pydevd", "pydevd_pycharm"):
        if name in sys.modules:
            return True
    if sys.gettrace() is not None:
        return True
    if os.environ.get("DEBUGPY_LAUNCHER_PORT") or os.environ.get("PYDEVD_USE_FRAME_EVAL"):
        return True
    return False


def _local_gguf_test_via_subprocess(settings: Dict[str, Any], wall_timeout: float) -> str:
    """Run load + ping in an isolated one-shot child process."""
    return _local_gguf_run_oneshot(settings, {"op": "ping"}, wall_timeout)


def llm_connection_test(
    provider: str,
    timeout_seconds: float,
    azure_openai: Dict[str, Any],
    openai_api: Dict[str, Any],
    local_gguf: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Minimal chat completion to verify endpoint, credentials, and deployment/model name.

    ``provider`` is one of ``azure_openai``, ``openai``, or ``local_gguf`` (aliases accepted).
    ``timeout_seconds`` is clamped 5–600. For **Local GGUF**, it is also the maximum wall-clock
    wait for model load plus one ping (minimum 90 s so short values do not abort mid-load).
    """
    t = max(5.0, min(600.0, float(timeout_seconds)))
    cfg = {
        "llm": {"provider": provider, "timeout_seconds": t},
        "azure_openai": dict(azure_openai or {}),
        "openai_api": dict(openai_api or {}),
        "local_gguf": dict(local_gguf or {}),
    }

    prov_norm = _PROVIDER_ALIASES.get(str(provider).lower(), str(provider).lower())
    if prov_norm == PROVIDER_LOCAL_GGUF:
        wall_timeout = max(90.0, min(600.0, t))
        settings = _local_gguf_settings(cfg)
        debugger_note = ""
        if _is_running_under_debugger():
            debugger_note = (
                "\nNOTE: a Python debugger (debugpy / VS Code / Cursor) is attached. "
                "The connection test was run in an isolated child process to avoid the "
                "native access-violation crashes that can happen when llama.cpp's worker "
                "threads race with the debugger's sys.settrace hook. For best results, "
                "launch gui_chat.py with python.exe directly (not via the debugger) when "
                "using a local GGUF model.\n"
            )

        try:
            text = _local_gguf_test_via_subprocess(settings, wall_timeout)
        except RuntimeError:
            raise
        preview = _safe_ascii_preview(text)
        return (
            f"Local GGUF check passed (isolated child process).\n\n"
            f"Model: {settings.get('model_path')}\n"
            f"Chat format: {settings.get('chat_format')}\n"
            f"n_ctx: {settings.get('n_ctx')} | n_gpu_layers: {settings.get('n_gpu_layers')}\n"
            f"Wall timeout used: {int(wall_timeout)} s (from Request timeout; minimum 90 s for local)\n"
            f"Response (ASCII preview): {preview!r}"
            f"{debugger_note}"
        )

    try:
        from openai import AzureOpenAI, OpenAI  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "OpenAI SDK not available. Install dependency: pip install openai"
        ) from e

    if prov_norm == PROVIDER_OPENAI:
        oa = cfg["openai_api"]
        api_key = (str(oa.get("api_key", "") or "").strip()) or os.environ.get("OPENAI_API_KEY", "").strip()
        model = (str(oa.get("model", "") or "").strip()) or os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
        base_url = (str(oa.get("base_url", "") or "").strip()) or os.environ.get("OPENAI_BASE_URL", "").strip()
        if not api_key:
            api_key = _env("OPENAI_API_KEY")
        if not model:
            model = "gpt-4o-mini"
        kwargs: Dict[str, Any] = {"api_key": api_key, "timeout": t}
        if base_url:
            kwargs["base_url"] = base_url.rstrip("/")
        client = OpenAI(**kwargs)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=_ping_messages(),
                max_tokens=16,
                temperature=0,
                timeout=t,
            )
        except Exception as e:
            if _is_timeout_error(e):
                raise RuntimeError(
                    f"OpenAI API did not respond within {int(t)} second(s). Check network and timeout."
                ) from e
            raise
        text = (resp.choices[0].message.content or "").strip()
        rid = getattr(resp, "id", "") or ""
        return (
            f"OpenAI API check passed.\n\n"
            f"Model: {model}\n"
            f"Response: {text!r}\n"
            f"Request id: {rid or '(n/a)'}"
        )

    aoai = cfg["azure_openai"]
    endpoint = (str(aoai.get("endpoint", "") or "").strip()) or os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
    api_key = (str(aoai.get("api_key", "") or "").strip()) or os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
    deployment = (str(aoai.get("deployment", "") or "").strip()) or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "").strip()
    api_version = (
        (str(aoai.get("api_version", "") or "").strip())
        or os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview").strip()
    )
    if not api_version:
        api_version = "2024-02-15-preview"
    if not endpoint:
        endpoint = _env("AZURE_OPENAI_ENDPOINT")
    if not api_key:
        api_key = _env("AZURE_OPENAI_API_KEY")
    if not deployment:
        deployment = _env("AZURE_OPENAI_DEPLOYMENT")

    client = AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=_normalize_azure_endpoint(endpoint),
        timeout=t,
    )
    try:
        resp = client.chat.completions.create(
            model=deployment,
            messages=_ping_messages(),
            max_tokens=16,
            temperature=0,
            timeout=t,
        )
    except Exception as e:
        if _is_timeout_error(e):
            raise RuntimeError(
                f"Azure OpenAI did not respond within {int(t)} second(s). Check network and timeout."
            ) from e
        raise
    text = (resp.choices[0].message.content or "").strip()
    rid = getattr(resp, "id", "") or ""
    return (
        f"Azure OpenAI check passed.\n\n"
        f"Deployment: {deployment}\n"
        f"Response: {text!r}\n"
        f"Request id: {rid or '(n/a)'}"
    )


def _analysis_system_prompt() -> str:
    return (
        "You analyze TestBench measurement RESULTS produced by a sequence of commands.\n"
        "Return ONLY raw JSON (no markdown, no code fences, no text before or after the object) with keys:\n"
        '- "analysis": string — concise interpretation of the results (key observations, trends, '
        "anomalies, units, pass/fail). Keep it short (≤6 sentences).\n"
        '- "plot": optional object or null. If a plot helps the user, set:\n'
        '    {"x": [..numbers..], "y": [..numbers..], "title": "...", '
        '"xlabel": "...", "ylabel": "...", "kind": "line"|"bar"|"scatter"}\n'
        "\n"
        "Rules:\n"
        "- Use ONLY values present in RESULTS — do not invent numbers.\n"
        "- If a 1D/2D series is already present in a result, reproduce it in plot.x/plot.y.\n"
        "- If only scalars are available across N commands, you may build a small bar chart "
        "(one bar per scalar; use the command label or short name as x and the scalar as y).\n"
        '- Omit "plot" or set it to null if no useful plot can be derived from RESULTS.\n'
        '- "x" and "y" must be arrays of equal length and contain numbers only.\n'
        '- Keep arrays short and complete (e.g. ≤ 256 points). Do not truncate '
        'arrays mid-stream; if the source is longer, downsample so x and y end '
        'with matching lengths.\n'
    )


def _truncate_for_prompt(text: str, max_chars: int = 1500) -> str:
    s = str(text)
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + f"...(truncated, {len(s) - max_chars} more chars)"


def _format_results_for_prompt(results: List[Dict[str, Any]]) -> str:
    """
    Compact text block of (command -> result/error) lines for the analysis prompt.

    ``results`` is a list of dicts with keys:
    - ``command``: original command text
    - ``result``: returned value (any JSON-serializable; truncated if huge)
    - ``error``:  optional error message string
    """
    if not results:
        return "(no results captured)"
    lines: List[str] = []
    for i, item in enumerate(results, 1):
        cmd = str((item or {}).get("command", "")).strip() or "(unknown command)"
        err = (item or {}).get("error")
        if err:
            lines.append(f"{i}. {cmd}\n   ERROR: {_truncate_for_prompt(err, 500)}")
            continue
        val = (item or {}).get("result", None)
        try:
            text = json.dumps(val, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            text = repr(val)
        lines.append(f"{i}. {cmd}\n   RESULT: {_truncate_for_prompt(text, 1500)}")
    return "\n".join(lines)


def _parse_analysis_response(content: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    raw = (content or "").strip()
    if not raw:
        raise RuntimeError("Model returned empty analysis response.")
    normalized = _normalize_llm_json_text(raw)
    if not normalized:
        raise RuntimeError("Model returned empty analysis response after stripping markdown.")
    try:
        payload: Dict[str, Any] = json.loads(normalized)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            "Model did not return valid JSON for analysis.\n"
            f"Raw content:\n{raw}"
        ) from e
    analysis = str(payload.get("analysis", "") or "").strip()
    plot = payload.get("plot")
    if plot in (None, "", {}):
        plot = None
    elif not isinstance(plot, dict):
        plot = None
    return analysis, plot


def _resolve_timeout_and_provider(cfg: Dict[str, Any]) -> Tuple[float, str]:
    llm = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    aoai = cfg.get("azure_openai") if isinstance(cfg.get("azure_openai"), dict) else {}
    oa = cfg.get("openai_api") if isinstance(cfg.get("openai_api"), dict) else {}
    timeout_sec = _parse_timeout_seconds(llm or {}, aoai or {}, oa or {})
    provider = _resolve_provider(cfg)
    return timeout_sec, provider


def _chat_completion_text(
    cfg: Dict[str, Any],
    messages: List[Dict[str, str]],
    timeout_sec: float,
    *,
    temperature: float = 0.2,
) -> str:
    """Provider-aware chat completion that returns the raw assistant content."""
    provider = _resolve_provider(cfg)
    if provider == PROVIDER_LOCAL_GGUF:
        return _local_gguf_chat(messages, cfg, temperature=temperature)
    if provider == PROVIDER_OPENAI:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "OpenAI SDK not available. Install dependency: pip install openai"
            ) from e
        oa = cfg.get("openai_api", {}) if isinstance(cfg, dict) else {}
        if not isinstance(oa, dict):
            oa = {}
        api_key = (str(oa.get("api_key", "") or "").strip()) or os.environ.get("OPENAI_API_KEY", "").strip()
        model = (str(oa.get("model", "") or "").strip()) or os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
        base_url = (str(oa.get("base_url", "") or "").strip()) or os.environ.get("OPENAI_BASE_URL", "").strip()
        if not api_key:
            api_key = _env("OPENAI_API_KEY")
        if not model:
            model = "gpt-4o-mini"
        kwargs: Dict[str, Any] = {"api_key": api_key, "timeout": timeout_sec}
        if base_url:
            kwargs["base_url"] = base_url.rstrip("/")
        client = OpenAI(**kwargs)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                timeout=timeout_sec,
            )
        except Exception as e:
            if _is_timeout_error(e):
                raise RuntimeError(
                    f"OpenAI API did not respond within {int(timeout_sec)} second(s). "
                    "Increase timeout in LLM settings or check network."
                ) from e
            raise
        return (resp.choices[0].message.content or "").strip()

    try:
        from openai import AzureOpenAI  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "OpenAI SDK not available. Install dependency: pip install openai"
        ) from e
    aoai = cfg.get("azure_openai", {}) if isinstance(cfg, dict) else {}
    if not isinstance(aoai, dict):
        aoai = {}
    endpoint = (str(aoai.get("endpoint", "") or "").strip()) or os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
    api_key = (str(aoai.get("api_key", "") or "").strip()) or os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
    deployment = (str(aoai.get("deployment", "") or "").strip()) or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "").strip()
    api_version = (
        (str(aoai.get("api_version", "") or "").strip())
        or os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview").strip()
    )
    if not api_version:
        api_version = "2024-02-15-preview"
    if not endpoint:
        endpoint = _env("AZURE_OPENAI_ENDPOINT")
    if not api_key:
        api_key = _env("AZURE_OPENAI_API_KEY")
    if not deployment:
        deployment = _env("AZURE_OPENAI_DEPLOYMENT")
    client = AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=_normalize_azure_endpoint(endpoint),
        timeout=timeout_sec,
    )
    try:
        resp = client.chat.completions.create(
            model=deployment,
            messages=messages,
            temperature=temperature,
            timeout=timeout_sec,
        )
    except Exception as e:
        if _is_timeout_error(e):
            raise RuntimeError(
                f"Azure OpenAI did not respond within {int(timeout_sec)} second(s). "
                "Increase timeout in LLM settings or check network and endpoint."
            ) from e
        raise
    return (resp.choices[0].message.content or "").strip()


def llm_analyze_results(
    user_text: str,
    results: List[Dict[str, Any]],
    registry: Any,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Send the executed-command RESULTS back to the LLM for a post-run analysis
    and (optionally) a plot specification.

    Returns ``(analysis_text, plot_spec_or_None)`` where ``plot_spec`` is a dict
    like ``{"x": [...], "y": [...], "title": "...", "xlabel": "...", "ylabel": "...", "kind": "line"}``
    suitable to pass to ``chat_plotting.render_plot_to_png_bytes``.
    """
    cfg: Dict[str, Any] = {}
    try:
        cfg_mgr = getattr(registry, "config_manager", None) if registry is not None else None
        cfg = getattr(cfg_mgr, "config", {}) if cfg_mgr is not None else {}
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}

    timeout_sec, _provider = _resolve_timeout_and_provider(cfg)

    rag_query = (user_text or "").strip()
    extra = _summarize_results_for_query(results)
    if extra:
        rag_query = (rag_query + "\n" + extra).strip() if rag_query else extra
    rag_block, _hits = retrieve_for_prompt(rag_query, cfg)

    user_content = (
        (f"CONTEXT:\n{rag_block}\n\n" if rag_block else "")
        + f"REQUEST:\n{(user_text or '').strip() or '(no original request)'}\n\n"
        + f"RESULTS:\n{_format_results_for_prompt(results)}"
    )
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": _analysis_system_prompt()},
        {"role": "user", "content": user_content},
    ]
    content = _chat_completion_text(cfg, messages, timeout_sec)
    return _parse_analysis_response(content)


def llm_chat_to_plan(
    user_text: str,
    registry: Any,
    *,
    conversation_turns: Optional[List[Dict[str, Any]]] = None,
    last_results: Optional[List[Dict[str, Any]]] = None,
    last_commands: Optional[List[str]] = None,
) -> Tuple[List[str], str]:
    """
    Dispatch to configured LLM provider. Config in bench JSON:

    - ``llm.provider``: ``azure_openai`` (default), ``openai``, or ``local_gguf``
    - ``llm.timeout_seconds``: optional global timeout (5–600 s)
    - ``azure_openai.*``: endpoint, deployment, api_version, api_key
    - ``openai_api.*``: api_key, model, base_url (optional; default OpenAI cloud if base_url empty)
    - ``local_gguf.*``: model_path, n_ctx, n_threads, n_gpu_layers, n_batch, chat_format, max_tokens

    Optional multi-turn context: ``conversation_turns``, ``last_results``, ``last_commands``.

    Environment fallbacks: standard Azure / ``OPENAI_*`` / ``LOCAL_GGUF_MODEL_PATH``.
    """
    cfg: Dict[str, Any] = {}
    try:
        cfg_mgr = getattr(registry, "config_manager", None) if registry is not None else None
        cfg = getattr(cfg_mgr, "config", {}) if cfg_mgr is not None else {}
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}

    llm = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    aoai = cfg.get("azure_openai") if isinstance(cfg.get("azure_openai"), dict) else {}
    oa = cfg.get("openai_api") if isinstance(cfg.get("openai_api"), dict) else {}

    timeout_sec = _parse_timeout_seconds(llm or {}, aoai or {}, oa or {})
    provider = _resolve_provider(cfg)

    ctx = {
        "conversation_turns": conversation_turns,
        "last_results": last_results,
        "last_commands": last_commands,
    }
    if provider == PROVIDER_LOCAL_GGUF:
        return _local_gguf_chat_to_plan(user_text, registry, cfg, **ctx)
    if provider == PROVIDER_OPENAI:
        return _openai_direct_chat_to_plan(user_text, registry, cfg, timeout_sec, **ctx)
    return _azure_chat_to_plan(user_text, registry, cfg, timeout_sec, **ctx)


def _repair_context(
    user_text: str,
    results: List[Dict[str, Any]],
    registry: Any,
    cfg: Dict[str, Any],
    *,
    last_commands: Optional[List[str]] = None,
    conversation_turns: Optional[List[Dict[str, Any]]] = None,
) -> str:
    allowed = build_allowed_commands_text(registry)
    rag_query = (user_text or "").strip()
    extra = _summarize_results_for_query(results)
    if extra:
        rag_query = (rag_query + "\n" + extra).strip() if rag_query else extra
    rag_block, _ = retrieve_for_prompt(rag_query, cfg)
    llm = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    max_hist = 8
    if isinstance(llm, dict):
        from testbench.llm_automation_loop import AutomationLoopConfig

        max_hist = AutomationLoopConfig.from_config(cfg).multi_turn_history
    turns = trim_conversation_turns(conversation_turns or [], max_hist)
    return build_repair_user_content(
        user_text,
        results,
        allowed,
        rag_block,
        last_commands=last_commands,
        conversation_turns=turns,
    )


def llm_repair_plan(
    user_text: str,
    results: List[Dict[str, Any]],
    registry: Any,
    *,
    last_commands: Optional[List[str]] = None,
    conversation_turns: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[str], str]:
    """
    Suggest minimal corrective commands after a failed run.

    Uses the same provider stack as :func:`llm_chat_to_plan`.
    """
    cfg: Dict[str, Any] = {}
    try:
        cfg_mgr = getattr(registry, "config_manager", None) if registry is not None else None
        cfg = getattr(cfg_mgr, "config", {}) if cfg_mgr is not None else {}
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}

    llm = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    aoai = cfg.get("azure_openai") if isinstance(cfg.get("azure_openai"), dict) else {}
    oa = cfg.get("openai_api") if isinstance(cfg.get("openai_api"), dict) else {}
    timeout_sec = _parse_timeout_seconds(llm or {}, aoai or {}, oa or {})

    user_content = _repair_context(
        user_text,
        results,
        registry,
        cfg,
        last_commands=last_commands,
        conversation_turns=conversation_turns,
    )
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": repair_system_prompt()},
        {"role": "user", "content": user_content},
    ]
    content = _chat_completion_text(cfg, messages, timeout_sec, temperature=0.15)
    return _parse_plan_response(content, cfg)
