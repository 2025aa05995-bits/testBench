import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from testbench.llm_chat import _parse_plan_response  # noqa: E402


def test_parse_fenced_json():
    raw = """```json
{
  "commands": [],
  "analysis": "No actionable request."
}
```"""
    cmds, analysis = _parse_plan_response(raw)
    assert cmds == []
    assert "actionable" in analysis.lower()


def test_parse_bare_json():
    cmds, analysis = _parse_plan_response('{"commands": ["bc.ps.on"], "analysis": "on"}')
    assert cmds == ["bc.ps.on"]
    assert analysis == "on"
