"""Shared automation-loop state and handlers for PyQt/Tk chat UIs."""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from testbench.llm_automation_loop import (
    AutomationLoopConfig,
    make_conversation_turn,
    results_need_repair,
    trim_conversation_turns,
)
from testbench.llm_chat import llm_chat_to_plan, llm_repair_plan

from gui_chat_support.command_helpers import (
    CHAT_MODE_AGENT,
    CHAT_MODE_PLAN,
    validate_llm_commands,
)


class AutomationLoopMixin:
    """
    Mixin for chat windows. Expects standard sequence/LLM attributes and methods:

    ``registry``, ``parser``, ``_chat_mode``, ``_sequence_origin``, ``_sequence_results``,
    ``_sequence_stopped_by_user``, ``_sequence_user_text``, ``_last_results``,
    ``_last_results_user_text``, ``_analysis_in_flight``, ``_append_text``, ``_append_error``,
    ``_start_command_sequence``, ``_on_llm_plan_ok``, ``_on_llm_plan_err``,
    ``update_status_bar``, and LLM worker emit helpers ``_emit_llm_plan_ok`` / ``_emit_llm_plan_err``.
    """

    def _update_status(self) -> None:
        fn = getattr(self, "update_status_bar", None) or getattr(self, "update_status_label", None)
        if callable(fn):
            fn()

    def _init_automation_loop(self) -> None:
        self._llm_conversation_turns: List[Dict[str, Any]] = []
        self._loop_iteration = 0
        self._loop_root_request = ""
        self._loop_last_commands: List[str] = []
        self._loop_last_analysis = ""
        self._pending_repair_mode = False
        self._loop_auto_repair = False
        self._automation_loop_deferred_analyze = False

    def _automation_config(self) -> AutomationLoopConfig:
        try:
            cfg = self.registry.config_manager.config or {}
        except Exception:
            cfg = {}
        return AutomationLoopConfig.from_config(cfg)

    def _reset_automation_loop_for_request(self, user_text: str) -> None:
        self._loop_iteration = 0
        self._loop_root_request = (user_text or "").strip()
        self._loop_last_commands = []
        self._loop_last_analysis = ""

    def _llm_plan_kwargs(self) -> Dict[str, Any]:
        cfg = self._automation_config()
        turns = trim_conversation_turns(self._llm_conversation_turns, cfg.multi_turn_history)
        return {
            "conversation_turns": turns,
            "last_results": list(self._last_results) if self._last_results else None,
            "last_commands": list(self._loop_last_commands) if self._loop_last_commands else None,
        }

    def _record_llm_conversation_turn(self) -> None:
        if self._sequence_origin != "llm":
            return
        if not self._sequence_results:
            return
        user = (self._loop_root_request or self._sequence_user_text or "").strip()
        cmds = list(self._loop_last_commands or [])
        turn = make_conversation_turn(
            user,
            cmds,
            list(self._sequence_results),
            analysis=self._loop_last_analysis,
        )
        self._llm_conversation_turns.append(turn)
        cfg = self._automation_config()
        self._llm_conversation_turns = trim_conversation_turns(
            self._llm_conversation_turns, cfg.multi_turn_history
        )

    def _clear_llm_conversation(self) -> None:
        self._llm_conversation_turns = []
        self._append_text("LLM conversation context cleared.\n\n")

    def _store_loop_commands(self, commands: List[str], analysis: str = "") -> None:
        self._loop_last_commands = list(commands or [])
        self._loop_last_analysis = (analysis or "").strip()

    def _maybe_continue_automation_loop(self) -> bool:
        """
        After a sequence finishes, optionally start a repair plan.

        Returns True if a repair LLM call was started (caller should skip analyze for now).
        """
        if self._sequence_stopped_by_user:
            return False
        if self._sequence_origin != "llm":
            return False
        cfg = self._automation_config()
        if not cfg.enabled:
            return False
        results = list(self._sequence_results or [])
        if not results_need_repair(results):
            return False
        if not cfg.auto_repair_on_fail:
            return False
        if self._chat_mode == CHAT_MODE_AGENT and not cfg.closed_loop_agent:
            return False
        if self._loop_iteration >= cfg.max_iterations:
            self._append_text(
                f"Automation loop: reached max repair iterations ({cfg.max_iterations}).\n\n"
            )
            return False
        if self._analysis_in_flight:
            return False

        self._loop_iteration += 1
        self._loop_auto_repair = True
        root = (self._loop_root_request or self._sequence_user_text or "").strip()
        self._append_text(
            f"Automation loop: failure detected — repair attempt "
            f"{self._loop_iteration}/{cfg.max_iterations}…\n"
        )
        self._start_llm_repair_bg(root, results)
        return True

    def _start_llm_repair_bg(self, user_text: str, results: List[Dict[str, Any]]) -> None:
        kwargs = self._llm_plan_kwargs()

        def _bg():
            try:
                commands, analysis = llm_repair_plan(
                    user_text,
                    results,
                    self.registry,
                    last_commands=self._loop_last_commands or None,
                    conversation_turns=kwargs.get("conversation_turns"),
                )
            except Exception as e:
                self._emit_llm_plan_err(f"LLM repair error: {e}")
                return
            self._emit_llm_plan_ok(commands, analysis, repair=True)

        threading.Thread(target=_bg, daemon=True).start()

    def _start_llm_plan_bg(self, raw_text: str) -> None:
        self._reset_automation_loop_for_request(raw_text)
        kwargs = self._llm_plan_kwargs()

        def _bg():
            try:
                commands, analysis = llm_chat_to_plan(raw_text, self.registry, **kwargs)
            except Exception as e:
                self._emit_llm_plan_err(f"LLM error: {e}")
                return
            self._emit_llm_plan_ok(commands, analysis, repair=False)

        threading.Thread(target=_bg, daemon=True).start()

    def _handle_repair_keyword(self, hint: str) -> None:
        if self._sequence_active:
            self._append_error("Cannot repair while a sequence is running.\n\n")
            return
        if not self._last_results:
            self._append_error(
                "Nothing to repair yet — run a bench/bc command or an LLM sequence first.\n\n"
            )
            return
        self._pending_repair_mode = True
        root = (self._loop_root_request or self._last_results_user_text or "").strip()
        user_text = (hint or "").strip() or root or "repair"
        self._append_text("Generating repair plan with LLM…\n")
        self._start_llm_repair_bg(user_text, list(self._last_results))

    def _on_llm_plan_ok_automation(
        self, commands, analysis, *, repair: bool = False
    ) -> None:
        """Shared plan/repair handler; call from ``_on_llm_plan_ok``."""
        analysis = str(analysis or "").strip()
        safe, err = validate_llm_commands(commands, self.parser)
        if err:
            self._pending_repair_mode = False
            self._append_error(f"{err}\n\n")
            if self._automation_loop_deferred_analyze:
                self._automation_loop_deferred_analyze = False
                self._record_llm_conversation_turn()
                self._maybe_run_post_analysis()
            return
        if not safe:
            self._pending_repair_mode = False
            if analysis:
                self._append_text(f"{analysis}\n\n")
            self._append_error("LLM returned no repair/plan commands.\n\n")
            if self._automation_loop_deferred_analyze:
                self._automation_loop_deferred_analyze = False
                self._record_llm_conversation_turn()
                self._maybe_run_post_analysis()
            return

        self._store_loop_commands(safe, analysis)
        auto_repair_run = (
            repair
            and self._loop_auto_repair
            and self._chat_mode == CHAT_MODE_AGENT
        )
        self._loop_auto_repair = False
        force_plan = (
            self._pending_repair_mode
            or self._chat_mode == CHAT_MODE_PLAN
            or (repair and not auto_repair_run)
        )
        self._pending_repair_mode = False

        if force_plan:
            label = "Repair plan" if repair else "Proposed commands"
            if analysis:
                self._append_text(f"{analysis}\n\n")
            self._append_text(f"{label}:\n")
            for i, c in enumerate(safe, 1):
                self._append_text(f"  {i}. {c}\n")
            self._append_text("\nType run (or go) to execute this plan, or discard to cancel.\n\n")
            self._pending_plan_commands = safe
            self._pending_plan_user_text = (
                self._loop_root_request or self._last_results_user_text or ""
            )
            self._update_status()
            return

        if analysis:
            self._append_text(f"{analysis}\n\n")
        if getattr(self, "_sequence_recording", False):
            self._sequence_record_buffer.extend(safe)
        self._update_status()
        ut = self._loop_root_request or getattr(self, "_pending_llm_user_text", "") or ""
        self._pending_llm_user_text = ""
        self._start_command_sequence(safe, origin="llm", user_text=ut)

    def _finish_sequence_automation_hook(self) -> bool:
        """
        Call at end of ``_finish_sequence`` before analyze.

        Returns True if analyze should be deferred (repair started).
        """
        if self._sequence_origin == "llm" and self._sequence_results:
            self._record_llm_conversation_turn()
        if self._maybe_continue_automation_loop():
            self._automation_loop_deferred_analyze = True
            return True
        if self._automation_loop_deferred_analyze:
            self._automation_loop_deferred_analyze = False
        return False
