"""LLM-backed natural language → TestBench command plans (multi-provider)."""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

# Config keys
PROVIDER_AZURE = "azure_openai"
PROVIDER_OPENAI = "openai"


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
    client = AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=endpoint,
        timeout=timeout_sec,
    )

    try:
        resp = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": _system_prompt()},
                {
                    "role": "user",
                    "content": f"ALLOWED:\n{allowed}\n\nREQUEST:\n{(user_text or '').strip()}",
                },
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
    kwargs: Dict[str, Any] = {"api_key": api_key, "timeout": timeout_sec}
    if base_url:
        kwargs["base_url"] = base_url.rstrip("/")

    client = OpenAI(**kwargs)

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _system_prompt()},
                {
                    "role": "user",
                    "content": f"ALLOWED:\n{allowed}\n\nREQUEST:\n{(user_text or '').strip()}",
                },
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


def _resolve_provider(cfg: Dict[str, Any]) -> str:
    llm = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    p = str((llm or {}).get("provider", "") or "").strip().lower()
    if p in (PROVIDER_AZURE, PROVIDER_OPENAI):
        return p
    return PROVIDER_AZURE


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
) -> str:
    """
    Minimal chat completion to verify endpoint, credentials, and deployment/model name.
    Uses the same resolution rules as ``llm_chat_to_plan`` (config dicts + env fallbacks).
    ``timeout_seconds`` is clamped 5–600.
    """
    try:
        from openai import AzureOpenAI, OpenAI  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "OpenAI SDK not available. Install dependency: pip install openai"
        ) from e

    t = max(5.0, min(600.0, float(timeout_seconds)))
    cfg = {
        "llm": {"provider": provider, "timeout_seconds": t},
        "azure_openai": dict(azure_openai or {}),
        "openai_api": dict(openai_api or {}),
    }

    if str(provider).lower() == PROVIDER_OPENAI:
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
        azure_endpoint=endpoint,
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
        azure_endpoint=endpoint,
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

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": _analysis_system_prompt()},
        {
            "role": "user",
            "content": (
                f"REQUEST:\n{(user_text or '').strip() or '(no original request)'}\n\n"
                f"RESULTS:\n{_format_results_for_prompt(results)}"
            ),
        },
    ]
    content = _chat_completion_text(cfg, messages, timeout_sec)
    return _parse_analysis_response(content)


def llm_chat_to_plan(user_text: str, registry: Any) -> Tuple[List[str], str]:
    """
    Dispatch to configured LLM provider. Config in bench JSON:

    - ``llm.provider``: ``azure_openai`` (default) or ``openai``
    - ``llm.timeout_seconds``: optional global timeout (5–600 s)
    - ``azure_openai.*``: endpoint, deployment, api_version, api_key, timeout_seconds (legacy)
    - ``openai_api.*``: api_key, model, base_url (optional; default OpenAI cloud if base_url empty)

    Environment fallbacks: standard Azure and OPENAI_* variables.
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

    if provider == PROVIDER_OPENAI:
        return _openai_direct_chat_to_plan(user_text, registry, cfg, timeout_sec)
    return _azure_chat_to_plan(user_text, registry, cfg, timeout_sec)
