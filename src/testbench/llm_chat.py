"""LLM-backed natural language → TestBench command plans (multi-provider)."""

import json
import os
import re
from typing import Any, Dict, List, Tuple

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
