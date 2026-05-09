"""LLM-backed natural language → TestBench command plans (multi-provider)."""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from testbench.rag import _summarize_results_for_query, retrieve_for_prompt

# Config keys
PROVIDER_AZURE = "azure_openai"
PROVIDER_OPENAI = "openai"
PROVIDER_LOCAL_GGUF = "local_gguf"

# Process-wide cache for the loaded llama.cpp model (heavy to construct).
_LOCAL_GGUF_LOCK: Any = None
_LOCAL_GGUF_CACHE: Dict[str, Any] = {}


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
    """Strip markdown fences (```json ... ```) and isolate a JSON object if needed."""
    s = (content or "").strip()
    if not s:
        return s
    fence = re.search(r"```(?:json)?\s*\r?\n?([\s\S]*?)\r?\n?```", s, re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()
    if s.startswith("{") and s.endswith("}"):
        return s
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        return s[start : end + 1].strip()
    return s


def _system_prompt() -> str:
    return (
        "You convert user requests into TestBench commands.\n"
        "Return ONLY raw JSON (no markdown, no code fences, no text before or after the object) with keys:\n"
        '- "commands": array of strings\n'
        '- "analysis": string\n'
        "\n"
        "Allowed command forms:\n"
        "- bench.<category>.<action> [args...]\n"
        "- bc.<category>.<action> [args...]\n"
        '- "delay <seconds>"\n'
        '- "help" or "help <category>"\n'
        '- plot <bench/bc command>  (or: plot "Label" <bench/bc command>)\n'
        '- quoted heading: "Title"\n'
        "\n"
        "Rules:\n"
        "- Do NOT invent categories/actions; use only items in ALLOWED.\n"
        "- Prefer bc.* unless the user explicitly asks for bench.*.\n"
        "- Every instrument command MUST be bc.<category>.<action> or bench.<category>.<action> "
        "(e.g. bc.osc.run). Never emit bare category.action like osc.run.\n"
        "- Keep commands minimal and safe; avoid raw SCPI unless user explicitly asks.\n"
        "- If a CONTEXT block is present, treat it as internal reference material "
        "(SOPs, datasheets, lab notes). Use it to choose parameters and order, but "
        "do NOT mention or quote it in the analysis text.\n"
    )


def _parse_plan_response(content: str) -> Tuple[List[str], str]:
    raw = (content or "").strip()
    if not raw:
        raise RuntimeError("Model returned empty response.")
    normalized = _normalize_llm_json_text(raw)
    if not normalized:
        raise RuntimeError("Model returned empty response after stripping markdown.")
    try:
        payload: Dict[str, Any] = json.loads(normalized)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            "Model did not return valid JSON. Update the prompt or reduce temperature.\n"
            f"Raw content:\n{raw}"
        ) from e

    commands_raw = payload.get("commands", [])
    if not isinstance(commands_raw, list):
        raise RuntimeError('Invalid JSON: "commands" must be an array of strings.')
    commands: List[str] = []
    for c in commands_raw:
        s = str(c).strip()
        if s:
            commands.append(s)

    analysis = payload.get("analysis", "")
    analysis = str(analysis).strip() if analysis is not None else ""
    return commands, analysis


def _azure_chat_to_plan(user_text: str, registry: Any, cfg: Dict[str, Any], timeout_sec: float) -> Tuple[List[str], str]:
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

    allowed = build_allowed_commands_text(registry)
    rag_block, _ = retrieve_for_prompt(user_text or "", cfg)
    client = AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=_normalize_azure_endpoint(endpoint),
        timeout=timeout_sec,
    )

    user_content = (
        (f"CONTEXT:\n{rag_block}\n\n" if rag_block else "")
        + f"ALLOWED:\n{allowed}\n\nREQUEST:\n{(user_text or '').strip()}"
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
    return _parse_plan_response(content)


def _openai_direct_chat_to_plan(user_text: str, registry: Any, cfg: Dict[str, Any], timeout_sec: float) -> Tuple[List[str], str]:
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

    allowed = build_allowed_commands_text(registry)
    rag_block, _ = retrieve_for_prompt(user_text or "", cfg)
    kwargs: Dict[str, Any] = {"api_key": api_key, "timeout": timeout_sec}
    if base_url:
        kwargs["base_url"] = base_url.rstrip("/")

    client = OpenAI(**kwargs)

    user_content = (
        (f"CONTEXT:\n{rag_block}\n\n" if rag_block else "")
        + f"ALLOWED:\n{allowed}\n\nREQUEST:\n{(user_text or '').strip()}"
    )
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
    return _parse_plan_response(content)


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

    def _int(key: str, default: int, lo: int, hi: int) -> int:
        v = raw.get(key)
        try:
            n = int(v) if v is not None and not (isinstance(v, str) and not v.strip()) else default
        except (TypeError, ValueError):
            n = default
        return max(lo, min(hi, n))

    chat_format = str(raw.get("chat_format", "") or "").strip().lower()
    if chat_format in {"", "auto"}:
        cf: Optional[str] = None
        low = model_path.lower()
        for tag, fmt in (
            ("gemma-3", "gemma"),
            ("gemma-2", "gemma"),
            ("gemma", "gemma"),
            ("llama-3", "llama-3"),
            ("llama3", "llama-3"),
            ("llama-2", "llama-2"),
            ("mistral", "mistral-instruct"),
            ("phi-3", "phi-3"),
            ("qwen", "qwen"),
        ):
            if tag in low:
                cf = fmt
                break
        chat_format = cf or "chatml"

    return {
        "model_path": model_path,
        "n_ctx": _int("n_ctx", 4096, 256, 131072),
        "n_threads": _int("n_threads", max(1, (os.cpu_count() or 4) // 2), 1, 128),
        "n_gpu_layers": _int("n_gpu_layers", 0, -1, 200),
        "n_batch": _int("n_batch", 256, 32, 4096),
        "max_tokens": _int("max_tokens", 1024, 16, 32768),
        "chat_format": chat_format,
        "verbose": bool(raw.get("verbose", False)),
    }


def _load_local_gguf_model(settings: Dict[str, Any]) -> Any:
    """Lazily load and cache a ``llama_cpp.Llama`` instance keyed by load args."""
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

    global _LOCAL_GGUF_LOCK
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
            model = Llama(
                model_path=model_path,
                n_ctx=int(settings.get("n_ctx", 4096)),
                n_threads=int(settings.get("n_threads", 4)),
                n_gpu_layers=int(settings.get("n_gpu_layers", 0)),
                n_batch=int(settings.get("n_batch", 256)),
                chat_format=str(settings.get("chat_format") or "chatml"),
                verbose=bool(settings.get("verbose", False)),
            )
        except Exception as e:
            raise RuntimeError(_format_local_gguf_load_error(model_path, e)) from e
        _LOCAL_GGUF_CACHE[key] = model
        return model


def _format_local_gguf_load_error(model_path: str, exc: BaseException) -> str:
    """Build a human-friendly hint for common ``Llama(...)`` failures.

    The native llama.cpp loader raises C++ exceptions / NULL-deref access
    violations when a GGUF was produced by a *newer* llama.cpp than the runtime
    bundled with the installed ``llama-cpp-python`` wheel. This mostly hits
    very fresh model families (e.g. Gemma 3), so we surface a concrete next
    step instead of the raw stack trace.
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

    if "gemma-3" in name or "gemma3" in name:
        extras.append(
            "Gemma 3 GGUFs require a very recent llama.cpp runtime. "
            "Upgrade with:  pip install --upgrade --prefer-binary llama-cpp-python"
        )
        extras.append(
            "If the upgrade still crashes, try a Gemma 2 build instead "
            "(e.g. gemma-2-2b-it-Q4_K_M.gguf), or a Llama-3 / Phi-3 / Qwen2.5 GGUF — "
            "those work with older runtimes."
        )
    elif is_access_violation:
        extras.append(
            "Access-violation crashes from the loader almost always mean the GGUF "
            "needs a newer llama.cpp than the installed wheel. "
            "Try:  pip install --upgrade --prefer-binary llama-cpp-python"
        )
        extras.append("Or pick a slightly older GGUF (e.g. Q4_K_M of Llama-3, Phi-3, Qwen2.5).")
    else:
        extras.append(
            "If this looks like a tokenizer or architecture error, upgrade "
            "llama-cpp-python or pick a different GGUF."
        )

    return (
        f"Failed to load GGUF model {model_path!r}: {msg}\n"
        + "\n".join(f"  - {x}" for x in extras)
    )


def _local_gguf_chat(
    messages: List[Dict[str, str]],
    cfg: Dict[str, Any],
    *,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    """Chat-completion shim around ``llama_cpp.Llama.create_chat_completion``."""
    settings = _local_gguf_settings(cfg)
    model = _load_local_gguf_model(settings)
    mt = int(max_tokens if max_tokens is not None else settings.get("max_tokens", 1024))
    try:
        resp = model.create_chat_completion(
            messages=messages,
            temperature=float(temperature),
            max_tokens=mt,
        )
    except Exception as e:
        raise RuntimeError(f"Local GGUF model error: {e}") from e
    try:
        return (resp["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Local GGUF model returned an unexpected response: {resp!r}") from e


def _local_gguf_chat_to_plan(user_text: str, registry: Any, cfg: Dict[str, Any]) -> Tuple[List[str], str]:
    allowed = build_allowed_commands_text(registry)
    rag_block, _ = retrieve_for_prompt(user_text or "", cfg)
    user_content = (
        (f"CONTEXT:\n{rag_block}\n\n" if rag_block else "")
        + f"ALLOWED:\n{allowed}\n\nREQUEST:\n{(user_text or '').strip()}"
    )
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": user_content},
    ]
    content = _local_gguf_chat(messages, cfg, temperature=0.2)
    return _parse_plan_response(content)


def _ping_messages() -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": "You are a connectivity check. Reply with exactly the single word OK and nothing else.",
        },
        {"role": "user", "content": "Ping."},
    ]


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
    ``timeout_seconds`` is clamped 5–600 for cloud providers and ignored for local GGUF.
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
        settings = _local_gguf_settings(cfg)
        try:
            text = _local_gguf_chat(_ping_messages(), cfg, temperature=0.0, max_tokens=16)
        except RuntimeError:
            raise
        return (
            f"Local GGUF check passed.\n\n"
            f"Model: {settings.get('model_path')}\n"
            f"Chat format: {settings.get('chat_format')}\n"
            f"n_ctx: {settings.get('n_ctx')} | n_gpu_layers: {settings.get('n_gpu_layers')}\n"
            f"Response: {text!r}"
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


def llm_chat_to_plan(user_text: str, registry: Any) -> Tuple[List[str], str]:
    """
    Dispatch to configured LLM provider. Config in bench JSON:

    - ``llm.provider``: ``azure_openai`` (default), ``openai``, or ``local_gguf``
    - ``llm.timeout_seconds``: optional global timeout (5–600 s)
    - ``azure_openai.*``: endpoint, deployment, api_version, api_key
    - ``openai_api.*``: api_key, model, base_url (optional; default OpenAI cloud if base_url empty)
    - ``local_gguf.*``: model_path, n_ctx, n_threads, n_gpu_layers, n_batch, chat_format, max_tokens

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

    if provider == PROVIDER_LOCAL_GGUF:
        return _local_gguf_chat_to_plan(user_text, registry, cfg)
    if provider == PROVIDER_OPENAI:
        return _openai_direct_chat_to_plan(user_text, registry, cfg, timeout_sec)
    return _azure_chat_to_plan(user_text, registry, cfg, timeout_sec)
