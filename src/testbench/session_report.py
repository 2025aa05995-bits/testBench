"""Structured session logging and JSON/HTML test reports."""

from __future__ import annotations

import json
import html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._paths import default_config_file, repo_root


@dataclass
class SessionEntry:
    index: int
    command: str
    status: str  # ok | error | pass | fail | heading | skip
    result: Any = None
    error: Optional[str] = None
    check: Optional[Dict[str, Any]] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SessionRecorder:
    """Records each executed command and aggregate pass/fail counts."""

    def __init__(self, config_path: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.config_path = str(config_path or default_config_file())
        self.metadata = dict(metadata or {})
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.entries: List[SessionEntry] = []
        self._index = 0

    def record(
        self,
        command: str,
        *,
        status: str = "ok",
        result: Any = None,
        error: Optional[str] = None,
        check: Optional[Dict[str, Any]] = None,
    ) -> SessionEntry:
        self._index += 1
        entry = SessionEntry(
            index=self._index,
            command=command,
            status=status,
            result=_json_safe(result),
            error=error,
            check=check,
        )
        self.entries.append(entry)
        return entry

    @property
    def pass_count(self) -> int:
        return sum(1 for e in self.entries if e.status == "pass")

    @property
    def fail_count(self) -> int:
        return sum(1 for e in self.entries if e.status == "fail")

    @property
    def error_count(self) -> int:
        return sum(1 for e in self.entries if e.status == "error")

    @property
    def verdict(self) -> str:
        if self.fail_count or self.error_count:
            return "FAIL"
        if self.pass_count:
            return "PASS"
        return "OK"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": "testbench.session.v1",
            "repo": str(repo_root()),
            "config": self.config_path,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "verdict": self.verdict,
            "summary": {
                "steps": len(self.entries),
                "pass": self.pass_count,
                "fail": self.fail_count,
                "error": self.error_count,
            },
            "metadata": self.metadata,
            "entries": [
                {
                    "index": e.index,
                    "timestamp": e.timestamp,
                    "command": e.command,
                    "status": e.status,
                    "result": e.result,
                    "error": e.error,
                    "check": e.check,
                }
                for e in self.entries
            ],
        }

    def export_json(self, path: str) -> str:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        p.write_text(text, encoding="utf-8")
        return str(p.resolve())

    def export_html(self, path: str) -> str:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        rows = []
        for e in data["entries"]:
            status = e["status"]
            cls = status
            detail = ""
            if e.get("check"):
                detail = html.escape(str(e["check"].get("message", "")))
            elif e.get("error"):
                detail = html.escape(str(e["error"]))
            elif e.get("result") is not None:
                detail = html.escape(str(e["result"])[:500])
            rows.append(
                f"<tr class='{cls}'><td>{e['index']}</td>"
                f"<td><code>{html.escape(e['command'])}</code></td>"
                f"<td>{html.escape(status)}</td>"
                f"<td>{detail}</td></tr>"
            )
        body = "\n".join(rows)
        doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Test Bench Report — {html.escape(data['verdict'])}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; }}
    h1 {{ margin-bottom: 0.25rem; }}
    .meta {{ color: #555; margin-bottom: 1rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; vertical-align: top; }}
    th {{ background: #f0f0f0; }}
    tr.pass td:nth-child(3) {{ color: #0a7a0a; font-weight: 600; }}
    tr.fail td:nth-child(3) {{ color: #b00020; font-weight: 600; }}
    tr.error td:nth-child(3) {{ color: #b00020; font-weight: 600; }}
    code {{ font-size: 0.9em; }}
  </style>
</head>
<body>
  <h1>Test Bench Session — {html.escape(data['verdict'])}</h1>
  <p class="meta">Started {html.escape(data['started_at'])} · Config {html.escape(data['config'])}</p>
  <p>Steps: {data['summary']['steps']} · Pass: {data['summary']['pass']} · Fail: {data['summary']['fail']} · Errors: {data['summary']['error']}</p>
  <table>
    <thead><tr><th>#</th><th>Command</th><th>Status</th><th>Detail</th></tr></thead>
    <tbody>
{body}
    </tbody>
  </table>
</body>
</html>
"""
        p.write_text(doc, encoding="utf-8")
        return str(p.resolve())


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)
