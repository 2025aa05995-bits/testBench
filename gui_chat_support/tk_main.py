"""Tkinter fallback Lab Automation Chat window and entrypoint."""

import json
import os
import re
import sys
import threading
from datetime import datetime
from functools import partial
from pathlib import Path

from testbench.chat_plotting import (
    plot_data_csv_path,
    render_plot_to_png_bytes,
    should_log_plot_data_as_csv,
    try_extract_plot_command,
    write_plot_series_csv,
)
from testbench.command_parser import CommandParser, handle_help
from testbench.command_registry import CommandRegistry
from testbench.runner import BenchRunner
from testbench._paths import default_config_file
from testbench.llm_automation_loop import AutomationLoopConfig
from testbench.llm_chat import (
    PROVIDER_AZURE,
    PROVIDER_LOCAL_GGUF,
    PROVIDER_OPENAI,
    llm_analyze_results,
    llm_chat_to_plan,
    llm_connection_test,
)

from gui_chat_support.assets import gui_app_assets_dir, gui_app_icon_path_preferred, windows_set_app_user_model_id
from gui_chat_support.constants import CONFIG_DIALOG_START, DEFAULT_GUI_FONT_PREFS, EXAMPLE_POWER_CYCLE_COMMANDS
from gui_chat_support.fonts import load_gui_font_preferences, save_gui_font_preferences
from gui_chat_support.sequences import load_test_sequences, save_test_sequences
from gui_chat_support.automation_loop import AutomationLoopMixin
from gui_chat_support.command_helpers import (
    CHAT_MODE_AGENT,
    CHAT_MODE_PLAN,
    CHAT_MODE_RAG,
    chat_mode_label,
    normalize_chat_mode,
    parse_analyze_keyword,
    parse_clear_llm_context_keyword,
    parse_plan_action,
    parse_rag_keyword,
    parse_repair_keyword,
    looks_like_direct_command,
    validate_llm_commands,
)
from testbench.rag import index_status, reload_index, retrieve_for_prompt
from testbench.rag_capture import capture_rag_sequence_from_input
from gui_chat_support.command_completer import CommandCompleter
from gui_chat_support.run_command import run_chat_command

_REPO_FILE = str(Path(__file__).resolve().parent.parent / "gui_chat.py")


try:
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter.scrolledtext import ScrolledText
    from tkinter import filedialog
    from tkinter import messagebox
    class ChatWindow(AutomationLoopMixin):
        def __init__(self):
            self.root = tk.Tk()
            self.root.title('Lab Automation Chat')
            _bg = '#e9ecef'
            _card = '#ffffff'
            _border = '#dee2e6'
            _text = '#212529'
            _muted = '#6c757d'
            _accent = '#0d6efd'
            _accent_hi = '#0b5ed7'
            self._tk_accent = _accent
            self._tk_accent_hi = _accent_hi
            self._tk_stop = '#dc3545'
            self._tk_stop_hi = '#bb2d3b'
            self.root.configure(bg=_bg)
            self._wm_icon_photo = None
            d = gui_app_assets_dir(_REPO_FILE)
            ico_p = os.path.join(d, 'lab_chat_icon.ico')
            png_p = os.path.join(d, 'lab_chat_icon.png')
            _icon_ok = False
            if sys.platform == 'win32' and os.path.isfile(ico_p):
                try:
                    self.root.iconbitmap(ico_p)
                    _icon_ok = True
                except Exception:
                    pass
            if not _icon_ok and os.path.isfile(png_p):
                try:
                    img = tk.PhotoImage(file=png_p)
                    self.root.iconphoto(True, img)
                    self._wm_icon_photo = img
                except Exception:
                    pass
            # Size window to ~75% of screen
            try:
                sw = self.root.winfo_screenwidth()
                sh = self.root.winfo_screenheight()
                w = int(sw * 0.75)
                h = int(sh * 0.75)
                x = int((sw - w) / 2)
                y = int((sh - h) / 2)
                self.root.geometry(f'{w}x{h}+{x}+{y}')
            except Exception:
                self.root.geometry('1000x750')

            self._font_prefs = load_gui_font_preferences()
            fp = self._font_prefs
            self._tk_menu_font = (fp['menu_family'], fp['menu_size'])
            self.menu = tk.Menu(self.root, font=self._tk_menu_font)
            self.root.config(menu=self.menu)

            file_menu = tk.Menu(self.menu, font=self._tk_menu_font)
            self.menu.add_cascade(label='File', menu=file_menu)
            file_menu.add_command(label='Save Log', command=self.save_log)
            file_menu.add_command(label='Load Config', command=self.load_config)
            file_menu.add_command(label='Exit', command=self.root.quit)

            scripts_menu = tk.Menu(self.menu, font=self._tk_menu_font)
            self.menu.add_cascade(label='Scripts', menu=scripts_menu)
            scripts_menu.add_command(label='Load Script', command=self.load_script)

            sequence_menu = tk.Menu(self.menu, tearoff=0, font=self._tk_menu_font)
            self.menu.add_cascade(label='Sequence', menu=sequence_menu)
            sequence_menu.add_command(label='Start', command=self._sequence_recording_start)
            sequence_menu.add_command(label='Stop', command=self._sequence_recording_stop)
            sequence_menu.add_command(label='Remove test sequence...', command=self._remove_test_sequence_dialog)

            self.test_sequence_menu = tk.Menu(self.menu, tearoff=0, font=self._tk_menu_font)
            self.menu.add_cascade(label='Test Sequence', menu=self.test_sequence_menu)

            settings_menu = tk.Menu(self.menu, font=self._tk_menu_font)
            self.menu.add_cascade(label='Settings', menu=settings_menu)
            settings_menu.add_command(label='Bench Settings', command=self.open_bench_settings)
            settings_menu.add_command(label='LLM settings…', command=self.open_llm_settings)
            settings_menu.add_command(label='Fonts…', command=self.open_font_settings)

            help_menu = tk.Menu(self.menu, font=self._tk_menu_font)
            self.menu.add_cascade(label='Help', menu=help_menu)
            help_menu.add_command(label='Show Commands', command=self.show_help)

            _mono_chat = (fp['chat_family'], fp['chat_size'])
            _mono_input = (fp['input_family'], fp['input_size'])
            _mono_suggest = (fp['suggestions_family'], fp['suggestions_size'])
            self.chat_display = ScrolledText(
                self.root,
                state='disabled',
                wrap='word',
                font=_mono_chat,
                bg=_card,
                fg=_text,
                relief='flat',
                highlightthickness=1,
                highlightbackground=_border,
                highlightcolor=_accent,
                padx=10,
                pady=10,
                insertbackground=_text,
            )
            self.chat_display.pack(fill='both', expand=True, padx=12, pady=12)
            self.chat_display.tag_configure('error', foreground='#c92a2a')
            self._heading_font = tkfont.Font(
                self.root,
                family=fp['chat_family'],
                size=max(6, int(fp['chat_size']) + 2),
                weight='bold',
                underline=True,
            )
            self.chat_display.tag_configure('heading', font=self._heading_font, foreground='#0c4a6e')

            self.mode_frame = tk.Frame(self.root, bg=_bg)
            self.mode_frame.pack(fill='x', padx=12, pady=(0, 4))
            tk.Label(self.mode_frame, text='LLM chat mode:', bg=_bg, fg=_text, font=(fp['menu_family'], fp['menu_size'])).pack(
                side='left', padx=(0, 8)
            )
            self._chat_mode_var = tk.StringVar(value='Agent')
            self._chat_mode_menu = tk.OptionMenu(
                self.mode_frame,
                self._chat_mode_var,
                'Agent',
                'Plan',
                'RAG',
                command=lambda *_a: self._on_chat_mode_changed(),
            )
            self._chat_mode_menu.pack(side='left')

            self.input_frame = tk.Frame(self.root, bg=_bg)
            self.input_frame.pack(fill='x', padx=12, pady=(0, 10))

            self.input_line = tk.Text(
                self.input_frame,
                height=3,
                wrap='word',
                font=_mono_input,
                bg=_card,
                fg=_text,
                relief='flat',
                highlightthickness=1,
                highlightbackground='#adb5bd',
                highlightcolor=_accent,
                padx=8,
                pady=6,
                insertbackground=_text,
            )
            self.input_line.pack(side='left', fill='x', expand=True, padx=(0, 10))
            self.input_line.bind('<Return>', self.on_text_return)
            self.input_line.bind('<KeyRelease>', self.on_input_changed)
            self.input_line.bind('<Up>', self.on_suggestion_up)
            self.input_line.bind('<Down>', self.on_suggestion_down)
            self.input_line.bind('<Tab>', self.on_suggestion_tab)

            self.action_frame = tk.Frame(self.input_frame, bg=_bg)
            self.action_frame.pack(side='right', fill='y')
            _btn_w = 10
            _btn_padx = 12
            _btn_pady = 8

            self.clear_button = tk.Button(
                self.action_frame,
                text='Clear',
                command=self.clear_screen,
                font=('Segoe UI', 9, 'bold'),
                width=_btn_w,
                bg=_card,
                fg=_muted,
                activebackground='#f8f9fa',
                activeforeground=_text,
                relief='solid',
                borderwidth=1,
                highlightthickness=0,
                padx=_btn_padx,
                pady=_btn_pady,
                cursor='hand2',
            )
            self.send_button = tk.Button(
                self.action_frame,
                text='Send',
                command=self._on_send_or_stop_clicked,
                font=('Segoe UI', 9, 'bold'),
                width=_btn_w,
                bg=_accent,
                fg='#ffffff',
                activebackground=_accent_hi,
                activeforeground='#ffffff',
                relief='flat',
                padx=_btn_padx,
                pady=_btn_pady,
                cursor='hand2',
            )
            self.send_button.pack(side='bottom')
            self.clear_button.pack(side='bottom', pady=(0, 8))

            self.suggestions_frame = tk.Frame(self.root, bg=_bg)
            self.suggestions_frame.pack(fill='x', padx=12, pady=(0, 8))

            self.suggestions_list = tk.Listbox(
                self.suggestions_frame,
                height=5,
                font=_mono_suggest,
                bg=_card,
                fg=_text,
                relief='flat',
                highlightthickness=1,
                highlightbackground=_border,
                selectbackground='#e7f1ff',
                selectforeground='#084298',
                activestyle='none',
            )
            self.suggestions_list.pack(fill='x')
            self.suggestions_list.bind('<Button-1>', self.on_suggestion_clicked)
            self.suggestions_list.bind('<Return>', self.on_suggestion_select)
            self.suggestions_list.pack_forget()

            self.status_label = tk.Label(
                self.root,
                text='',
                anchor='w',
                bg=_card,
                fg=_muted,
                font=(fp['status_family'], fp['status_size']),
                relief='flat',
                highlightthickness=1,
                highlightbackground=_border,
                padx=10,
                pady=6,
            )
            self.status_label.pack(fill='x', padx=12, pady=(0, 10))

            self.parser = CommandParser()
            self.registry = CommandRegistry()
            self.completer = CommandCompleter(self.registry)
            self.selected_suggestion_index = -1

            self._command_history = []
            self._history_max = 5
            self._history_browse_index = None
            self._history_setting_text = False

            self._sequence_active = False
            self._sequence_queue = []
            self._sequence_index = 0
            self._sequence_recording = False
            self._sequence_record_buffer = []
            self._sequence_origin = "user"
            self._sequence_results: list = []
            self._sequence_user_text = ""
            self._pending_llm_user_text = ""
            self._pending_plan_commands = None
            self._pending_plan_user_text = ""
            self._chat_mode = CHAT_MODE_AGENT
            self._analysis_in_flight = False
            self._sequence_stopped_by_user = False
            self._last_results: list = []
            self._last_results_user_text = ""
            self._test_sequences = load_test_sequences()
            self._delay_after_id = None
            self._pending_step_after_id = None
            self._init_automation_loop()

            self._append_text('Lab Automation Chat\n')
            self._append_text("Type 'help' for available commands\n")
            self._append_text("Type 'bench.' or 'bc.' to see command suggestions\n")
            self._append_text("Use semicolons or Shift+Enter for multiple commands.\n")
            self._append_text("Use bench.config.* to manage real/sim mode and discovery.\n")
            self._append_text("Use bench.<inst>.raw <SCPI> for raw instrument commands in real mode.\n")
            self._append_text(
                "Plot: plot bc.sg.measure frequency — scalar; 1D/2D series → logs/plot_data/*.csv "
                '(name in filename: plot "Test Data" bc.osc.get_trace 1); '
                "plot bc.osc.get_trace 1 after bc.osc.run (plot(...) still works).\n"
            )
            self._append_text(
                "Analyze: type 'analyze' to re-analyze the last sequence's results "
                "(optionally 'analyze <follow-up question>'). LLM-generated sequences auto-analyze unless disabled in Settings → LLM settings.\n"
            )
            self._append_text(
                "LLM chat mode (above): Agent runs proposals immediately; Plan shows commands first — "
                "then type run or discard. Default can be set under Settings → LLM settings.\n"
            )
            self._append_text(
                "Automation loop: failed LLM runs can auto-repair (Agent mode); type 'repair' or "
                "'repair <hint>' for a manual fix plan; 'clear llm' resets multi-turn context.\n"
            )
            self._append_text(
                "RAG: drop reference docs in rag_docs/. Use 'rag <query>' to preview matches, "
                "'rag reload' to reindex, 'rag status' for the current index.\n"
            )
            self._append_text(
                "RAG mode (toolbar): optional tag line + bc.* commands — saved to "
                "rag_docs/sequences/ for LLM context (no LLM call).\n"
            )
            self._append_text("History: Up/Down recalls last commands (when suggestions are hidden).\n")
            self._append_text('Section heading: wrap the title in double quotes, e.g. "Power Cycle Test".\n')
            self._append_text('Delay: use delay 10 to wait 10 seconds before the next command; Send becomes Stop.\n')
            self._append_text(
                'Sequence menu: Start records commands; Stop asks for category and name; '
                'Remove deletes a saved sequence. Saved items appear under Test Sequence by category.\n'
            )
            self._append_text('=' * 60 + '\n\n')

            self.update_status_label()
            self._rebuild_test_sequence_menu()
            self._apply_chat_mode_from_config()
            self._sync_chat_mode_var()

        def _apply_chat_mode_from_config(self) -> None:
            llm = self.registry.config_manager.config.get('llm') or {}
            if not isinstance(llm, dict):
                llm = {}
            self._chat_mode = normalize_chat_mode(llm.get('chat_mode'))

        def _sync_chat_mode_var(self) -> None:
            self._chat_mode_var.set(chat_mode_label(self._chat_mode))

        def _on_chat_mode_changed(self) -> None:
            self._chat_mode = normalize_chat_mode(self._chat_mode_var.get())
            self.update_status_label()

        def _clear_pending_plan(self) -> None:
            self._pending_plan_commands = None
            self._pending_plan_user_text = ""

        def _rebuild_test_sequence_menu(self) -> None:
            m = self.test_sequence_menu
            m.delete(0, tk.END)
            examples = tk.Menu(m, tearoff=0, font=self._tk_menu_font)
            m.add_cascade(label='Examples', menu=examples)
            examples.add_command(
                label='Power cycle (1s on/off)',
                command=lambda: self._run_stored_command_list(list(EXAMPLE_POWER_CYCLE_COMMANDS)),
            )
            cats = self._test_sequences.get('categories') or {}
            for cat in sorted(cats.keys()):
                sub = tk.Menu(m, tearoff=0, font=self._tk_menu_font)
                m.add_cascade(label=cat, menu=sub)
                for name in sorted((cats[cat] or {}).keys()):
                    sub.add_command(
                        label=name,
                        command=lambda c=cat, n=name: self._run_named_sequence(c, n),
                    )

        def _run_stored_command_list(self, commands: list) -> None:
            if self._sequence_active:
                messagebox.showwarning('Sequence running', 'Stop the current sequence before starting another.')
                return
            self._start_command_sequence(list(commands), origin="user")

        def _run_named_sequence(self, category: str, name: str) -> None:
            cmds = ((self._test_sequences.get('categories') or {}).get(category) or {}).get(name)
            if not cmds:
                messagebox.showwarning('Missing sequence', f'No saved commands for {category!r} / {name!r}.')
                return
            self._run_stored_command_list(list(cmds))

        def _prompt_category_and_name_tk(self, title: str):
            result = {'ok': False, 'cat': '', 'name': ''}
            top = tk.Toplevel(self.root)
            top.title(title)
            top.transient(self.root)
            top.grab_set()
            tk.Label(top, text='Category').grid(row=0, column=0, sticky='w', padx=8, pady=4)
            e_cat = tk.Entry(top, width=40)
            e_cat.grid(row=0, column=1, padx=8, pady=4)
            e_cat.insert(0, 'power_cycle')
            tk.Label(top, text='Name').grid(row=1, column=0, sticky='w', padx=8, pady=4)
            e_name = tk.Entry(top, width=40)
            e_name.grid(row=1, column=1, padx=8, pady=4)

            def on_ok():
                cat = e_cat.get().strip()
                name = e_name.get().strip()
                if not cat or not name:
                    messagebox.showwarning(title, 'Category and name must both be non-empty.', parent=top)
                    return
                result['ok'] = True
                result['cat'] = cat
                result['name'] = name
                top.destroy()

            def on_cancel():
                top.destroy()

            bf = tk.Frame(top)
            bf.grid(row=2, column=0, columnspan=2, pady=8)
            tk.Button(bf, text='OK', command=on_ok).pack(side='left', padx=4)
            tk.Button(bf, text='Cancel', command=on_cancel).pack(side='left', padx=4)
            top.wait_window()
            if result['ok']:
                return result['cat'], result['name']
            return None, None

        def _remove_test_sequence_dialog(self) -> None:
            cats = self._test_sequences.get('categories') or {}
            flat = [(c, n) for c in sorted(cats) for n in sorted((cats.get(c) or {}).keys())]
            if not flat:
                messagebox.showinfo('Remove test sequence', 'No saved test sequences to remove.')
                return
            top = tk.Toplevel(self.root)
            top.title('Remove test sequence')
            top.transient(self.root)
            top.grab_set()
            tk.Label(top, text='Select a sequence to remove:').pack(anchor='w', padx=8, pady=4)
            lb = tk.Listbox(top, height=min(14, len(flat)), width=48)
            for c, n in flat:
                lb.insert(tk.END, f'{c} → {n}')
            lb.pack(padx=8, pady=4)
            if flat:
                lb.selection_set(0)

            def do_remove():
                sel = lb.curselection()
                if not sel:
                    messagebox.showwarning('Remove test sequence', 'Select an entry in the list.', parent=top)
                    return
                category, name = flat[sel[0]]
                if not messagebox.askyesno(
                    'Confirm remove',
                    f'Remove sequence {category!r} / {name!r}?',
                    parent=top,
                ):
                    return
                cat_map = self._test_sequences.setdefault('categories', {})
                if category in cat_map and name in cat_map[category]:
                    del cat_map[category][name]
                    if not cat_map[category]:
                        del cat_map[category]
                try:
                    save_test_sequences(self._test_sequences)
                except OSError as e:
                    messagebox.showerror('Save failed', str(e), parent=top)
                    return
                top.destroy()
                self._rebuild_test_sequence_menu()
                self._append_text(f'Removed test sequence {category!r} / {name!r}.\n\n')

            bf = tk.Frame(top)
            bf.pack(pady=8)
            tk.Button(bf, text='Remove', command=do_remove).pack(side='left', padx=4)
            tk.Button(bf, text='Cancel', command=top.destroy).pack(side='left', padx=4)

        def _sequence_recording_start(self) -> None:
            if self._sequence_active:
                messagebox.showwarning('Sequence running', 'Stop the running sequence before starting recording.')
                return
            self._sequence_recording = True
            self._sequence_record_buffer = []
            self._append_text(
                f'[{self._timestamp()}] Sequence recording started. Send commands; use Sequence → Stop to save.\n\n'
            )

        def _sequence_recording_stop(self) -> None:
            if not self._sequence_recording:
                messagebox.showinfo('Sequence', 'Recording is not active. Choose Sequence → Start first.')
                return
            self._sequence_recording = False
            if not self._sequence_record_buffer:
                messagebox.showwarning(
                    'Save test sequence', 'Nothing was recorded. Use Start, then send at least one command.'
                )
                self._sequence_record_buffer = []
                return
            category, name = self._prompt_category_and_name_tk('Save test sequence')
            if category is None:
                self._append_text('Sequence recording cancelled (not saved).\n\n')
                self._sequence_record_buffer = []
                return
            self._test_sequences.setdefault('categories', {}).setdefault(category, {})[name] = list(
                self._sequence_record_buffer
            )
            try:
                save_test_sequences(self._test_sequences)
            except OSError as e:
                messagebox.showerror('Save failed', str(e))
                self._sequence_record_buffer = []
                return
            self._sequence_record_buffer = []
            self._rebuild_test_sequence_menu()
            self._append_text(
                f'Saved test sequence {name!r} under category {category!r} (Test Sequence → {category}).\n\n'
            )

        def _set_run_button_sequence_mode(self, running: bool) -> None:
            if running:
                self.send_button.config(
                    text='Stop',
                    bg=self._tk_stop,
                    activebackground=self._tk_stop_hi,
                )
            else:
                self.send_button.config(
                    text='Send',
                    bg=self._tk_accent,
                    activebackground=self._tk_accent_hi,
                )

        def _cancel_after_id(self, attr: str) -> None:
            aid = getattr(self, attr, None)
            if aid is not None:
                try:
                    self.root.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)

        def _cancel_all_sequence_timers(self) -> None:
            self._cancel_after_id('_delay_after_id')
            self._cancel_after_id('_pending_step_after_id')

        def _on_send_or_stop_clicked(self) -> None:
            if self._sequence_active:
                self._cancel_all_sequence_timers()
                self._sequence_stopped_by_user = True
                self._append_text('Sequence stopped.\n\n')
                self._finish_sequence()
            else:
                self.send_command()

        def _finish_sequence(self) -> None:
            self._cancel_all_sequence_timers()
            self._sequence_active = False
            self._sequence_queue = []
            self._sequence_index = 0
            self._set_run_button_sequence_mode(False)
            self.update_status_label()
            if self._sequence_results:
                self._last_results = list(self._sequence_results)
                self._last_results_user_text = self._sequence_user_text
            if self._finish_sequence_automation_hook():
                return
            self._maybe_run_post_analysis()

        def _emit_llm_plan_ok(self, commands, analysis, repair: bool = False) -> None:
            def _apply():
                self._on_llm_plan_ok_automation(commands, analysis, repair=repair)

            self.root.after(0, _apply)

        def _emit_llm_plan_err(self, msg: str) -> None:
            self.root.after(0, lambda: self._append_error(f"{msg}\n\n"))

        def _schedule_next_sequence_step(self, delay_ms: int = 0) -> None:
            self._cancel_after_id('_pending_step_after_id')
            self._pending_step_after_id = self.root.after(delay_ms, self._run_next_sequence_step)

        def _on_delay_elapsed(self) -> None:
            self._delay_after_id = None
            if self._sequence_active:
                self._run_next_sequence_step()

        def _start_command_sequence(self, commands: list, origin: str = "user", user_text: str = "") -> None:
            if origin == "llm" and commands:
                self._store_loop_commands(list(commands))
            try:
                runner = BenchRunner(registry=self.registry, parser=self.parser)
                commands = runner.expand(list(commands))
            except ValueError as e:
                self._append_error(f"Sequence expand error: {e}\n\n")
                return
            self._sequence_active = True
            self._sequence_queue = list(commands)
            self._sequence_index = 0
            self._sequence_origin = origin if origin in ("llm", "user") else "user"
            self._sequence_results = []
            self._sequence_stopped_by_user = False
            if origin == "llm":
                self._sequence_user_text = (user_text or "").strip()
            self._set_run_button_sequence_mode(True)
            self._run_next_sequence_step()

        def _record_command_result(self, command: str, *, result=None, error=None) -> None:
            """Capture executed-command outcomes for both auto- and manual-analysis."""
            entry = {"command": command}
            if error is not None:
                entry["error"] = str(error)
            else:
                entry["result"] = result
            self._sequence_results.append(entry)

        def _auto_analyze_enabled(self) -> bool:
            try:
                cfg = self.registry.config_manager.config or {}
                llm = cfg.get("llm") or {}
                if not isinstance(llm, dict):
                    return True
                v = llm.get("auto_analyze_results", True)
                if isinstance(v, bool):
                    return v
                if isinstance(v, str):
                    return v.strip().lower() not in {"false", "0", "no", "off"}
                return bool(v)
            except Exception:
                return True

        def _run_analyze_now(self, extra_prompt: str = "") -> None:
            """Manually re-analyze the most recent captured sequence results."""
            if self._sequence_active:
                self._append_error("Cannot analyze while a sequence is running.\n\n")
                return
            if self._analysis_in_flight:
                self._append_text("(Analysis already in progress…)\n\n")
                return
            if not self._last_results:
                self._append_error(
                    "Nothing to analyze yet — run a bench/bc command or an LLM request first.\n\n"
                )
                return
            extra = (extra_prompt or "").strip()
            base = (self._last_results_user_text or "").strip()
            if extra and base:
                user_text = f"{base}\n\nFollow-up: {extra}"
            else:
                user_text = extra or base
            results = list(self._last_results)
            self._analysis_in_flight = True
            self._append_text("Analyzing results with LLM...\n")

            def _bg():
                try:
                    analysis, plot_spec = llm_analyze_results(user_text, results, self.registry)
                except Exception as e:
                    self.root.after(0, lambda: self._on_llm_analysis_err(f"LLM analysis error: {e}"))
                    return
                self.root.after(0, lambda a=analysis or "", p=plot_spec: self._on_llm_analysis_ok(a, p))

            threading.Thread(target=_bg, daemon=True).start()

        def _maybe_run_post_analysis(self) -> None:
            """If the just-finished sequence came from an LLM plan, send results back for analysis."""
            if self._sequence_origin != "llm":
                return
            if self._analysis_in_flight:
                return
            if not self._sequence_results:
                return
            if self._sequence_stopped_by_user:
                return
            if not self._auto_analyze_enabled():
                return
            user_text = self._sequence_user_text
            results = list(self._sequence_results)
            self._analysis_in_flight = True
            self._append_text("Analyzing results with LLM...\n")

            def _bg():
                try:
                    analysis, plot_spec = llm_analyze_results(user_text, results, self.registry)
                except Exception as e:
                    self.root.after(0, lambda: self._on_llm_analysis_err(f"LLM analysis error: {e}"))
                    return
                self.root.after(0, lambda a=analysis or "", p=plot_spec: self._on_llm_analysis_ok(a, p))

            threading.Thread(target=_bg, daemon=True).start()

        def _on_llm_analysis_err(self, msg: str) -> None:
            self._analysis_in_flight = False
            self._append_error(f"{msg}\n\n")

        def _on_llm_analysis_ok(self, analysis: str, plot_spec) -> None:
            self._analysis_in_flight = False
            text = (analysis or "").strip()
            if text:
                self._append_heading("Analysis")
                self._append_text(text + "\n\n")
            elif plot_spec is None:
                self._append_text("(LLM produced no analysis or plot.)\n\n")
            if isinstance(plot_spec, dict):
                self._append_plot_from_data(plot_spec)
                self._append_text("\n")

        def _run_next_sequence_step(self) -> None:
            self._pending_step_after_id = None
            if not self._sequence_active:
                return
            if self._sequence_index >= len(self._sequence_queue):
                self._finish_sequence()
                return
            command = self._sequence_queue[self._sequence_index]
            self._sequence_index += 1
            self._append_text(f'[{self._timestamp()}] You: {command}\n')

            parts = command.strip().split(None, 1)
            if parts and parts[0].lower() == 'delay':
                if len(parts) < 2:
                    self._append_error('Usage: delay <seconds>\n\n')
                    self._schedule_next_sequence_step(0)
                    return
                try:
                    sec = float(parts[1].strip())
                except ValueError:
                    self._append_error(f'Invalid delay value: {parts[1]!r}\n\n')
                    self._schedule_next_sequence_step(0)
                    return
                if sec < 0:
                    self._append_error('Delay must be non-negative.\n\n')
                    self._schedule_next_sequence_step(0)
                    return
                ms = int(min(sec * 1000.0, 86400000))
                ms = max(ms, 0)
                self._cancel_after_id('_delay_after_id')
                self._delay_after_id = self.root.after(ms, self._on_delay_elapsed)
                return

            run_chat_command(
                command,
                self.registry,
                self.parser,
                self._append_text,
                self._append_error,
                self._append_heading,
                self._append_plot_from_data,
                record_result=self._record_command_result,
            )
            if not self._sequence_active:
                return
            self._schedule_next_sequence_step(0)

        def _history_append(self, text: str) -> None:
            t = (text or "").strip()
            if not t:
                return
            if self._command_history and self._command_history[-1] == t:
                return
            self._command_history.append(t)
            self._command_history = self._command_history[-self._history_max :]

        def _set_input_programmatic(self, text: str) -> None:
            self._history_setting_text = True
            try:
                self.input_line.delete('1.0', tk.END)
                self.input_line.insert('1.0', text)
                self.input_line.mark_set(tk.INSERT, tk.END)
                self.on_input_changed()
            finally:
                self._history_setting_text = False

        def _history_up(self) -> None:
            if not self._command_history:
                return
            if self._history_browse_index is None:
                self._history_browse_index = len(self._command_history) - 1
            elif self._history_browse_index > 0:
                self._history_browse_index -= 1
            else:
                return
            self._set_input_programmatic(self._command_history[self._history_browse_index])

        def _history_down(self) -> None:
            if self._history_browse_index is None:
                return
            if self._history_browse_index < len(self._command_history) - 1:
                self._history_browse_index += 1
                self._set_input_programmatic(self._command_history[self._history_browse_index])
            else:
                self._history_browse_index = None
                self._set_input_programmatic("")

        def _get_last_fragment(self, text: str) -> str:
            return re.split(r'[;\n\r]+', text)[-1].strip()

        def _apply_suggestion(self, suggestion: str) -> None:
            suggestion = (suggestion or "").strip()
            if not suggestion:
                return
            text = self.input_line.get('1.0', tk.END)
            parts = re.split(r'([;\n\r]+)', text)
            if not parts:
                new_text = suggestion
            else:
                if len(parts) == 1:
                    parts[0] = suggestion
                else:
                    parts[-1] = suggestion
                new_text = ''.join(parts)
            self.input_line.delete('1.0', tk.END)
            self.input_line.insert('1.0', new_text.strip())
            self.input_line.mark_set(tk.INSERT, tk.END)
            self.suggestions_list.pack_forget()
            self._history_browse_index = None

        def on_input_changed(self, event=None):
            if not self._history_setting_text:
                if event is None or getattr(event, 'keysym', '') not in ('Up', 'Down'):
                    self._history_browse_index = None
            text = self.input_line.get('1.0', tk.END).strip()
            last_fragment = self._get_last_fragment(text)
            if last_fragment.startswith(('bench.', 'bc.')):
                suggestions = self.completer.get_suggestions(text)
                self._update_suggestions(suggestions)
            else:
                self.suggestions_list.pack_forget()

        def _update_suggestions(self, suggestions):
            self.suggestions_list.delete(0, tk.END)
            if suggestions:
                for suggestion in suggestions:
                    self.suggestions_list.insert(tk.END, suggestion)
                self.suggestions_list.pack(fill='x')
                self.selected_suggestion_index = -1
            else:
                self.suggestions_list.pack_forget()

        def on_suggestion_up(self, event=None):
            if self.suggestions_list.winfo_ismapped():
                count = self.suggestions_list.size()
                if count > 0:
                    current = self.suggestions_list.curselection()
                    if current:
                        idx = current[0] - 1
                    else:
                        idx = count - 1
                    if idx < 0:
                        idx = count - 1
                    self.suggestions_list.selection_clear(0, tk.END)
                    self.suggestions_list.selection_set(idx)
                    self.suggestions_list.see(idx)
                    return 'break'
            self._history_up()
            return 'break'

        def on_suggestion_down(self, event=None):
            if self.suggestions_list.winfo_ismapped():
                count = self.suggestions_list.size()
                if count > 0:
                    current = self.suggestions_list.curselection()
                    if current:
                        idx = (current[0] + 1) % count
                    else:
                        idx = 0
                    self.suggestions_list.selection_clear(0, tk.END)
                    self.suggestions_list.selection_set(idx)
                    self.suggestions_list.see(idx)
                    return 'break'
            self._history_down()
            return 'break'

        def on_suggestion_clicked(self, event):
            selection = self.suggestions_list.curselection()
            if selection:
                suggestion = self.suggestions_list.get(selection[0])
                self._apply_suggestion(suggestion)

        def on_suggestion_select(self, event):
            selection = self.suggestions_list.curselection()
            if selection:
                suggestion = self.suggestions_list.get(selection[0])
                self._apply_suggestion(suggestion)
            return 'break'

        def on_suggestion_tab(self, event=None):
            if self.suggestions_list.winfo_ismapped():
                selection = self.suggestions_list.curselection()
                if selection:
                    suggestion = self.suggestions_list.get(selection[0])
                    self._apply_suggestion(suggestion)
                    return 'break'
            return 'break'

        def on_text_return(self, event=None):
            if event.state & 0x0001:
                self.input_line.insert('insert', '\n')
                return 'break'
            if self._sequence_active:
                return 'break'
            if self.suggestions_list.winfo_ismapped():
                selection = self.suggestions_list.curselection()
                if selection:
                    suggestion = self.suggestions_list.get(selection[0])
                    self._apply_suggestion(suggestion)
                    return 'break'
            self.send_command()
            return 'break'

        def send_command(self):
            if self._sequence_active:
                return
            raw_text = self.input_line.get('1.0', tk.END).strip()
            if not raw_text:
                return

            pa = parse_plan_action(raw_text)
            if self._pending_plan_commands is not None and pa is not None:
                self.suggestions_list.pack_forget()
                self._history_append(raw_text)
                self._history_browse_index = None
                self.input_line.delete('1.0', tk.END)
                self.update_status_label()
                self._append_text(f'[{self._timestamp()}] You: {raw_text}\n')
                cmds = self._pending_plan_commands
                ut = self._pending_plan_user_text
                self._clear_pending_plan()
                if pa == "run":
                    self._store_loop_commands(cmds)
                    if self._sequence_recording:
                        self._sequence_record_buffer.extend(cmds)
                    self.update_status_label()
                    self._start_command_sequence(cmds, origin="llm", user_text=ut)
                else:
                    self._append_text("Plan discarded.\n\n")
                    self.update_status_label()
                return

            if self._pending_plan_commands is not None:
                if looks_like_direct_command(raw_text):
                    self._clear_pending_plan()
                    self._append_text("(Pending plan cleared — running direct commands.)\n\n")
                elif not looks_like_direct_command(raw_text):
                    self._clear_pending_plan()
                    self._append_text("(Previous plan discarded.)\n\n")

            self.suggestions_list.pack_forget()
            self._history_append(raw_text)
            self._history_browse_index = None
            self.input_line.delete('1.0', tk.END)
            self.update_status_label()

            analyze_extra = parse_analyze_keyword(raw_text)
            if analyze_extra is not None:
                self._append_text(f'[{self._timestamp()}] You: {raw_text}\n')
                self._run_analyze_now(analyze_extra)
                return

            repair_hint = parse_repair_keyword(raw_text)
            if repair_hint is not None:
                self._append_text(f'[{self._timestamp()}] You: {raw_text}\n')
                self._handle_repair_keyword(repair_hint)
                return

            if parse_clear_llm_context_keyword(raw_text):
                self._append_text(f'[{self._timestamp()}] You: {raw_text}\n')
                self._clear_llm_conversation()
                return

            rag_action = parse_rag_keyword(raw_text)
            if rag_action is not None:
                self._append_text(f'[{self._timestamp()}] You: {raw_text}\n')
                self._handle_rag_command(*rag_action)
                return

            if self._chat_mode == CHAT_MODE_RAG:
                self._append_text(f'[{self._timestamp()}] You: {raw_text}\n')
                self._handle_rag_mode_capture(raw_text)
                return

            if not looks_like_direct_command(raw_text):
                self._append_text(f'[{self._timestamp()}] You: {raw_text}\n')
                self._append_text("Generating commands with LLM...\n")
                self._pending_llm_user_text = raw_text
                self._start_llm_plan_bg(raw_text)
                return

            commands = [cmd.strip() for cmd in re.split(r'[;\n\r]+', raw_text) if cmd.strip()]
            if self._sequence_recording:
                self._sequence_record_buffer.extend(commands)
            if not commands:
                return
            self._start_command_sequence(commands, origin="user")

        def _append_text(self, text: str):
            self.chat_display.configure(state='normal')
            self.chat_display.insert('end', text)
            self.chat_display.configure(state='disabled')
            self.chat_display.see('end')

        def _append_heading(self, title: str) -> None:
            title = (title or "").strip()
            if not title:
                return
            self.chat_display.configure(state='normal')
            self.chat_display.insert('end', title + '\n', 'heading')
            line = '─' * min(72, max(24, len(title)))
            self.chat_display.insert('end', line + '\n\n')
            self.chat_display.configure(state='disabled')
            self.chat_display.see('end')

        def clear_screen(self):
            self.chat_display.configure(state='normal')
            self.chat_display.delete('1.0', tk.END)
            self.chat_display.configure(state='disabled')

        def _timestamp(self) -> str:
            return datetime.now().strftime('%H:%M:%S')

        def _append_error(self, text: str):
            self.chat_display.configure(state='normal')
            self.chat_display.insert('end', text, "error")
            self.chat_display.configure(state='disabled')
            self.chat_display.see('end')

        def _append_plot_from_data(self, data):
            try:
                png = render_plot_to_png_bytes(data)
            except Exception as e:
                self._append_error(f'Plot error: {e}\n\n')
                return
            try:
                from io import BytesIO
                from PIL import Image, ImageTk

                img = Image.open(BytesIO(png))
                max_w = max(320, min(720, self.root.winfo_width() - 80))
                if img.width > max_w:
                    h = int(img.height * (max_w / img.width))
                    img = img.resize((max_w, h), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.chat_display.configure(state='normal')
                self.chat_display.image_create('end', image=photo)
                self.chat_display.insert('end', '\n')
                if not hasattr(self, '_plot_photos'):
                    self._plot_photos = []
                self._plot_photos.append(photo)
                self.chat_display.configure(state='disabled')
                self.chat_display.see('end')
            except Exception as e:
                self._append_error(f'Plot error (image embed): {e}\n\n')

        def update_status_label(self):
            simulate_dict = self.registry.config_manager.config.get('simulate', {})
            simulate_values = list(simulate_dict.values())
            if all(s for s in simulate_values):
                mode = "Simulated"
            elif not any(s for s in simulate_values):
                mode = "Real"
            else:
                mode = "Mixed"
            instruments = ", ".join(sorted([k for k in self.registry.instruments.keys() if k != 'config']))
            chat_label = chat_mode_label(self._chat_mode)
            pending = " | Plan pending" if self._pending_plan_commands else ""
            self.status_label.config(
                text=f"Mode: {mode} | Instruments: {instruments} | LLM chat: {chat_label}{pending}"
            )

        def save_log(self):
            text = self.chat_display.get('1.0', tk.END)
            filename = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text Files', '*.txt'), ('All Files', '*')])
            if filename:
                with open(filename, 'w') as f:
                    f.write(text)

        def load_config(self):
            filename = filedialog.askopenfilename(
                title='Load Config',
                initialdir=CONFIG_DIALOG_START,
                filetypes=[('JSON Files', '*.json'), ('All Files', '*.*')]
            )
            if not filename:
                return

            try:
                self.registry.config_manager.load_config(filename)
                self.registry.reload_instruments()
                self.completer = CommandCompleter(self.registry)
                self._apply_chat_mode_from_config()
                self._sync_chat_mode_var()
                self.update_status_label()
                self.on_input_changed()
                self._append_text(f'Loaded config: {filename}\n\n')
            except Exception as e:
                self._append_error(f'Error loading config: {e}\n\n')

        def load_script(self):
            filename = filedialog.askopenfilename(
                title='Load Script',
                filetypes=[
                    ('Script Files', '*.txt *.bench *.script *.cmd'),
                    ('Text Files', '*.txt'),
                    ('All Files', '*.*'),
                ]
            )
            if not filename:
                return

            try:
                with open(filename, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                self._history_browse_index = None
                self._history_setting_text = True
                try:
                    self.input_line.delete('1.0', tk.END)
                    self.input_line.insert('1.0', content.strip())
                    self.input_line.see(tk.END)
                    self.on_input_changed()
                finally:
                    self._history_setting_text = False
                self._append_text(f'Loaded script into command box: {filename}\n\n')
            except Exception as e:
                self._append_error(f'Error loading script: {e}\n\n')

        def open_bench_settings(self):
            top = tk.Toplevel(self.root)
            top.title('Bench Settings')
            top.geometry('700x500')

            path = getattr(self.registry.config_manager, 'config_file', str(default_config_file()))
            tk.Label(top, text=f'Editing: {path}', anchor='w').pack(fill='x', padx=8, pady=(8, 4))

            editor = ScrolledText(top, wrap='word')
            editor.pack(fill='both', expand=True, padx=8, pady=8)
            try:
                editor.insert('1.0', json.dumps(self.registry.config_manager.config, indent=2))
            except Exception:
                editor.insert('1.0', str(self.registry.config_manager.config))

            btn_frame = tk.Frame(top)
            btn_frame.pack(fill='x', padx=8, pady=(0, 8))

            def do_save_and_close():
                try:
                    new_cfg = json.loads(editor.get('1.0', tk.END))
                except Exception as exc:
                    messagebox.showerror('Invalid JSON', str(exc), parent=top)
                    return

                try:
                    self.registry.config_manager.config = new_cfg
                    self.registry.config_manager.save_config()
                    self.registry.config_manager.load_config()
                    self.registry.reload_instruments()
                    self.completer = CommandCompleter(self.registry)
                    self._apply_chat_mode_from_config()
                    self._sync_chat_mode_var()
                    self.update_status_label()
                    self.on_input_changed()
                    self._append_text('Bench settings saved and reloaded.\n\n')
                    top.destroy()
                except Exception as exc:
                    messagebox.showerror('Save failed', str(exc), parent=top)

            tk.Button(btn_frame, text='Save', command=do_save_and_close).pack(side='left')
            tk.Button(btn_frame, text='Cancel', command=top.destroy).pack(side='left', padx=(8, 0))

        def open_llm_settings(self):
            top = tk.Toplevel(self.root)
            top.title('LLM settings')
            top.geometry('860x560')
            top.minsize(780, 480)

            path = getattr(self.registry.config_manager, 'config_file', str(default_config_file()))
            tk.Label(top, text=f'Config: {path}', anchor='w').pack(fill='x', padx=8, pady=(8, 2))
            tk.Label(
                top,
                text='Natural-language chat → command generation. Pick provider and credentials.',
                anchor='w',
            ).pack(fill='x', padx=8, pady=(0, 6))

            cfg = self.registry.config_manager.config or {}
            llm = cfg.get('llm') or {}
            if not isinstance(llm, dict):
                llm = {}
            aoai = cfg.get('azure_openai') or {}
            if not isinstance(aoai, dict):
                aoai = {}
            oa = cfg.get('openai_api') or {}
            if not isinstance(oa, dict):
                oa = {}
            lg = cfg.get('local_gguf') or {}
            if not isinstance(lg, dict):
                lg = {}

            def _timeout_value() -> int:
                for d in (llm, aoai, oa):
                    if isinstance(d, dict) and d.get('timeout_seconds') is not None:
                        try:
                            return max(5, min(600, int(float(d['timeout_seconds']))))
                        except (TypeError, ValueError):
                            pass
                return 60

            prov_row = tk.Frame(top)
            prov_row.pack(fill='x', padx=10, pady=4)
            tk.Label(prov_row, text='Provider:', width=14, anchor='w').pack(side='left')
            _p = str(llm.get('provider', PROVIDER_AZURE) or PROVIDER_AZURE).lower()
            if _p == PROVIDER_OPENAI:
                _initial = PROVIDER_OPENAI
            elif _p == PROVIDER_LOCAL_GGUF:
                _initial = PROVIDER_LOCAL_GGUF
            else:
                _initial = PROVIDER_AZURE
            prov_var = tk.StringVar(value=_initial)

            def row(parent, label: str, value: str, show: str = None):
                r = tk.Frame(parent)
                r.pack(fill='x', pady=3)
                tk.Label(r, text=label, width=14, anchor='w').pack(side='left')
                e = tk.Entry(r, show=show) if show else tk.Entry(r)
                e.pack(side='left', fill='x', expand=True)
                e.insert(0, value or '')
                return e

            tk.Radiobutton(
                prov_row, text='Azure OpenAI', variable=prov_var, value=PROVIDER_AZURE
            ).pack(side='left', padx=(0, 12))
            tk.Radiobutton(
                prov_row, text='OpenAI (direct API)', variable=prov_var, value=PROVIDER_OPENAI
            ).pack(side='left', padx=(0, 12))
            tk.Radiobutton(
                prov_row, text='Local GGUF (llama.cpp)', variable=prov_var, value=PROVIDER_LOCAL_GGUF
            ).pack(side='left')

            rto = tk.Frame(top)
            rto.pack(fill='x', padx=10, pady=4)
            tk.Label(rto, text='Timeout (sec)', width=14, anchor='w').pack(side='left')
            timeout_var = tk.StringVar(value=str(_timeout_value()))
            tk.Spinbox(rto, from_=5, to=600, textvariable=timeout_var, width=8).pack(side='left')
            tk.Label(rto, text='seconds', anchor='w').pack(side='left', padx=(6, 0))
            tk.Label(
                top,
                text=(
                    'Cloud: timeout per request. Local GGUF: same value caps load+test time (min 90 s); '
                    'first load is often 30–120 s — use 180–300 s if the test times out.'
                ),
                anchor='w',
                justify='left',
                wraplength=560,
            ).pack(fill='x', padx=10, pady=(0, 4))

            aa_row = tk.Frame(top)
            aa_row.pack(fill='x', padx=10, pady=4)
            _aa_default = llm.get('auto_analyze_results', True)
            if isinstance(_aa_default, str):
                _aa_default = _aa_default.strip().lower() not in {'false', '0', 'no', 'off'}
            auto_analyze_var = tk.BooleanVar(value=bool(_aa_default))
            tk.Checkbutton(
                aa_row,
                text='Send results back to LLM for analysis and plot',
                variable=auto_analyze_var,
                anchor='w',
            ).pack(side='left')

            cm_row = tk.Frame(top)
            cm_row.pack(fill='x', padx=10, pady=4)
            tk.Label(cm_row, text='Default chat mode', width=14, anchor='w').pack(side='left')
            cm_cur = normalize_chat_mode(llm.get('chat_mode'))
            chat_mode_var = tk.StringVar(value=chat_mode_label(cm_cur))
            tk.OptionMenu(cm_row, chat_mode_var, 'Agent', 'Plan', 'RAG').pack(side='left')
            tk.Label(
                cm_row,
                text='(RAG = save manual sequences, no LLM)',
                anchor='w',
                fg='#495057',
            ).pack(side='left', padx=(12, 0))

            loop_cfg = AutomationLoopConfig.from_config(cfg)
            loop_row = tk.Frame(top)
            loop_row.pack(fill='x', padx=10, pady=4)
            auto_loop_var = tk.BooleanVar(value=loop_cfg.enabled)
            tk.Checkbutton(
                loop_row,
                text='Automation loop (auto-repair on FAIL/error)',
                variable=auto_loop_var,
                anchor='w',
            ).pack(side='left')
            iter_row = tk.Frame(top)
            iter_row.pack(fill='x', padx=10, pady=2)
            tk.Label(iter_row, text='Max repair iterations', width=18, anchor='w').pack(side='left')
            max_iter_var = tk.StringVar(value=str(loop_cfg.max_iterations))
            tk.Spinbox(iter_row, from_=1, to=10, textvariable=max_iter_var, width=6).pack(side='left')
            ar_row = tk.Frame(top)
            ar_row.pack(fill='x', padx=10, pady=2)
            auto_repair_var = tk.BooleanVar(value=loop_cfg.auto_repair_on_fail)
            tk.Checkbutton(ar_row, text='Auto-repair on failure', variable=auto_repair_var, anchor='w').pack(
                side='left'
            )
            cl_row = tk.Frame(top)
            cl_row.pack(fill='x', padx=10, pady=2)
            closed_loop_var = tk.BooleanVar(value=loop_cfg.closed_loop_agent)
            tk.Checkbutton(
                cl_row,
                text='Closed-loop Agent (auto-run repair steps)',
                variable=closed_loop_var,
                anchor='w',
            ).pack(side='left')
            hist_row = tk.Frame(top)
            hist_row.pack(fill='x', padx=10, pady=2)
            tk.Label(hist_row, text='Multi-turn history', width=18, anchor='w').pack(side='left')
            history_var = tk.StringVar(value=str(loop_cfg.multi_turn_history))
            tk.Spinbox(hist_row, from_=0, to=32, textvariable=history_var, width=6).pack(side='left')

            body = tk.Frame(top)
            body.pack(fill='both', expand=True, padx=10, pady=6)

            azure_frm = tk.LabelFrame(body, text='Azure OpenAI', padx=8, pady=6)
            endpoint = row(azure_frm, 'endpoint', str(aoai.get('endpoint', '') or ''))
            deployment = row(azure_frm, 'deployment', str(aoai.get('deployment', '') or ''))
            api_version = row(
                azure_frm,
                'api_version',
                str(aoai.get('api_version', '2024-02-15-preview') or '2024-02-15-preview'),
            )
            api_key_az = row(azure_frm, 'api_key', str(aoai.get('api_key', '') or ''), show='*')

            oa_frm = tk.LabelFrame(body, text='OpenAI (direct API)', padx=8, pady=6)
            api_key_oa = row(oa_frm, 'api_key', str(oa.get('api_key', '') or ''), show='*')
            model_e = row(oa_frm, 'model', str(oa.get('model', '') or 'gpt-4o-mini'))
            base_e = row(oa_frm, 'base_url', str(oa.get('base_url', '') or ''))
            tk.Label(
                oa_frm,
                text='Leave base URL empty for default OpenAI. Optional for compatible proxies.',
                anchor='w',
                justify='left',
                wraplength=560,
            ).pack(fill='x', pady=(4, 0))

            lg_frm = tk.LabelFrame(body, text='Local GGUF (llama.cpp)', padx=8, pady=6)

            path_row_frm = tk.Frame(lg_frm)
            path_row_frm.pack(fill='x', pady=3)
            tk.Label(path_row_frm, text='model_path', width=14, anchor='w').pack(side='left')
            lg_path_e = tk.Entry(path_row_frm, width=64)
            lg_path_e.pack(side='left', fill='x', expand=True, ipady=2)
            lg_path_e.insert(0, str(lg.get('model_path', '') or ''))
            try:
                lg_path_e.xview_moveto(1.0)
            except Exception:
                pass

            def _pick_gguf_tk():
                start = lg_path_e.get().strip()
                init_dir = os.path.dirname(start) if start and os.path.isfile(start) else ''
                picked = filedialog.askopenfilename(
                    parent=top,
                    title='Select GGUF model',
                    initialdir=init_dir or None,
                    filetypes=[('GGUF models', '*.gguf'), ('All files', '*.*')],
                )
                if picked:
                    lg_path_e.delete(0, tk.END)
                    lg_path_e.insert(0, picked)
                    try:
                        lg_path_e.xview_moveto(1.0)
                    except Exception:
                        pass

            tk.Button(path_row_frm, text='Browse…', command=_pick_gguf_tk).pack(side='left', padx=(8, 0))

            cf_row = tk.Frame(lg_frm)
            cf_row.pack(fill='x', pady=3)
            tk.Label(cf_row, text='chat_format', width=14, anchor='w').pack(side='left')
            cf_var = tk.StringVar(value=str(lg.get('chat_format', 'auto') or 'auto').lower())
            tk.OptionMenu(
                cf_row,
                cf_var,
                'auto', 'gemma-3', 'gemma', 'llama-3', 'llama-2', 'mistral-instruct', 'phi-3', 'qwen', 'chatml',
            ).pack(side='left')

            def _spin(parent, label, value, lo, hi, step=1):
                r = tk.Frame(parent)
                r.pack(fill='x', pady=3)
                tk.Label(r, text=label, width=14, anchor='w').pack(side='left')
                v = tk.StringVar(value=str(value))
                tk.Spinbox(r, from_=lo, to=hi, increment=step, textvariable=v, width=10).pack(side='left')
                return v

            try:
                _ctx_d = int(lg.get('n_ctx', 4096) or 4096)
            except (TypeError, ValueError):
                _ctx_d = 4096
            try:
                _gpu_d = int(lg.get('n_gpu_layers', 0) or 0)
            except (TypeError, ValueError):
                _gpu_d = 0
            try:
                _thr_d = int(lg.get('n_threads', 0) or 0)
            except (TypeError, ValueError):
                _thr_d = 0
            try:
                _mt_d = int(lg.get('max_tokens', 1024) or 1024)
            except (TypeError, ValueError):
                _mt_d = 1024

            n_ctx_var = _spin(lg_frm, 'n_ctx', _ctx_d, 256, 131072, 256)
            n_gpu_var = _spin(lg_frm, 'n_gpu_layers', _gpu_d, -1, 200, 1)
            n_threads_var = _spin(lg_frm, 'n_threads', _thr_d, 0, 128, 1)
            max_tokens_var = _spin(lg_frm, 'max_tokens', _mt_d, 16, 32768, 64)

            tk.Label(
                lg_frm,
                text=(
                    'Runs a local .gguf model via llama-cpp-python '
                    '("pip install llama-cpp-python"). For Gemma try a Q4_K_M / Q5_K_M GGUF.'
                ),
                anchor='w',
                justify='left',
                wraplength=560,
            ).pack(fill='x', pady=(4, 0))

            def _refresh_provider_frames(*_args):
                for f in (azure_frm, oa_frm, lg_frm):
                    f.pack_forget()
                v = prov_var.get()
                if v == PROVIDER_OPENAI:
                    oa_frm.pack(fill='both', expand=True)
                elif v == PROVIDER_LOCAL_GGUF:
                    lg_frm.pack(fill='both', expand=True)
                else:
                    azure_frm.pack(fill='both', expand=True)

            prov_var.trace_add('write', _refresh_provider_frames)
            _refresh_provider_frames()

            tk.Label(
                top,
                text='Timeout applies to both providers (env: OPENAI_TIMEOUT_SECONDS).',
                anchor='w',
                justify='left',
                wraplength=620,
            ).pack(fill='x', padx=10, pady=(0, 4))

            btnf = tk.Frame(top)
            btnf.pack(fill='x', padx=10, pady=(0, 10))

            def _local_gguf_dict_tk():
                def _i(var, default):
                    try:
                        return int(float(var.get()))
                    except (TypeError, ValueError):
                        return default
                return {
                    'model_path': lg_path_e.get().strip(),
                    'chat_format': cf_var.get().strip().lower() or 'auto',
                    'n_ctx': _i(n_ctx_var, 4096),
                    'n_gpu_layers': _i(n_gpu_var, 0),
                    'n_threads': _i(n_threads_var, 0),
                    'max_tokens': _i(max_tokens_var, 1024),
                    'verbose': bool(lg.get('verbose', False)),
                }

            def do_save_and_close():
                try:
                    try:
                        _tsec = int(float(timeout_var.get()))
                    except (TypeError, ValueError):
                        messagebox.showwarning('LLM settings', 'Invalid timeout; use 5–600 seconds.', parent=top)
                        return
                    _tsec = max(5, min(600, _tsec))
                    cfg = self.registry.config_manager.config or {}
                    prov = prov_var.get()
                    if prov not in (PROVIDER_AZURE, PROVIDER_OPENAI, PROVIDER_LOCAL_GGUF):
                        prov = PROVIDER_AZURE
                    try:
                        _max_iter = max(1, min(10, int(max_iter_var.get())))
                    except (TypeError, ValueError):
                        _max_iter = 3
                    try:
                        _hist = max(0, min(32, int(history_var.get())))
                    except (TypeError, ValueError):
                        _hist = 8
                    cfg['llm'] = {
                        'provider': prov,
                        'timeout_seconds': _tsec,
                        'auto_analyze_results': bool(auto_analyze_var.get()),
                        'chat_mode': normalize_chat_mode(chat_mode_var.get()),
                        'automation_loop': {
                            'enabled': bool(auto_loop_var.get()),
                            'max_iterations': _max_iter,
                            'auto_repair_on_fail': bool(auto_repair_var.get()),
                            'closed_loop_agent': bool(closed_loop_var.get()),
                            'multi_turn_history': _hist,
                        },
                    }
                    cfg['azure_openai'] = {
                        'endpoint': endpoint.get().strip(),
                        'deployment': deployment.get().strip(),
                        'api_version': api_version.get().strip() or '2024-02-15-preview',
                        'api_key': api_key_az.get().strip(),
                    }
                    cfg['openai_api'] = {
                        'api_key': api_key_oa.get().strip(),
                        'model': model_e.get().strip() or 'gpt-4o-mini',
                        'base_url': base_e.get().strip(),
                    }
                    cfg['local_gguf'] = _local_gguf_dict_tk()
                    self.registry.config_manager.config = cfg
                    self.registry.config_manager.save_config()
                    self.registry.config_manager.load_config()
                    self._apply_chat_mode_from_config()
                    self._sync_chat_mode_var()
                    self._append_text('LLM settings saved.\n\n')
                    top.destroy()
                except Exception as exc:
                    messagebox.showerror('Save failed', str(exc), parent=top)

            def do_test_connection():
                try:
                    _tsec = int(float(timeout_var.get()))
                except (TypeError, ValueError):
                    messagebox.showwarning('LLM settings', 'Invalid timeout; use 5–600 seconds.', parent=top)
                    return
                _tsec = max(5, min(600, _tsec))
                prov = prov_var.get()
                if prov not in (PROVIDER_AZURE, PROVIDER_OPENAI, PROVIDER_LOCAL_GGUF):
                    prov = PROVIDER_AZURE

                test_b.configure(state='disabled', text='Testing…')

                _watch = {'cancel': None, 'armed': True}

                def _watchdog() -> None:
                    if not _watch['armed']:
                        return
                    if str(test_b.cget('text')) == 'Testing…':
                        test_b.configure(state='normal', text='Test connection')
                        messagebox.showwarning(
                            'LLM test failed',
                            'The connection test did not finish within 5 minutes.\n\n'
                            'For Local GGUF: check the .gguf path, try a smaller model, '
                            'or increase timeout (e.g. 180–300 s).',
                            parent=top,
                        )

                _watch['cancel'] = self.root.after(300_000, _watchdog)

                def _finish_ok(m: str) -> None:
                    _watch['armed'] = False
                    c = _watch['cancel']
                    if c is not None:
                        try:
                            self.root.after_cancel(c)
                        except Exception:
                            pass
                    test_b.configure(state='normal', text='Test connection')
                    messagebox.showinfo('LLM test', m, parent=top)

                def _finish_err(err: str) -> None:
                    _watch['armed'] = False
                    c = _watch['cancel']
                    if c is not None:
                        try:
                            self.root.after_cancel(c)
                        except Exception:
                            pass
                    test_b.configure(state='normal', text='Test connection')
                    messagebox.showwarning('LLM test failed', err, parent=top)

                local_gguf_dict = _local_gguf_dict_tk()

                def _bg():
                    try:
                        msg = llm_connection_test(
                            prov,
                            float(_tsec),
                            {
                                'endpoint': endpoint.get().strip(),
                                'deployment': deployment.get().strip(),
                                'api_version': api_version.get().strip() or '2024-02-15-preview',
                                'api_key': api_key_az.get().strip(),
                            },
                            {
                                'api_key': api_key_oa.get().strip(),
                                'model': model_e.get().strip() or 'gpt-4o-mini',
                                'base_url': base_e.get().strip(),
                            },
                            local_gguf_dict,
                        )
                        self.root.after(0, lambda m=msg: _finish_ok(m))
                    except BaseException as e:
                        err = str(e).strip() or type(e).__name__
                        self.root.after(0, lambda err=err: _finish_err(err))

                threading.Thread(target=_bg, daemon=True).start()

            test_b = tk.Button(btnf, text='Test connection', command=do_test_connection)
            test_b.pack(side='left')
            tk.Button(btnf, text='Save', command=do_save_and_close).pack(side='left', padx=(8, 0))
            tk.Button(btnf, text='Cancel', command=top.destroy).pack(side='left', padx=(8, 0))

        def _apply_font_preferences_tk(self) -> None:
            fp = self._font_prefs
            self.chat_display.configure(font=(fp['chat_family'], fp['chat_size']))
            self.input_line.configure(font=(fp['input_family'], fp['input_size']))
            self.suggestions_list.configure(font=(fp['suggestions_family'], fp['suggestions_size']))
            self.status_label.configure(font=(fp['status_family'], fp['status_size']))
            self._heading_font.configure(
                family=fp['chat_family'],
                size=max(6, int(fp['chat_size']) + 2),
            )
            self.chat_display.tag_configure('heading', font=self._heading_font, foreground='#0c4a6e')

        def open_font_settings(self) -> None:
            top = tk.Toplevel(self.root)
            top.title('Font settings')
            top.transient(self.root)
            top.grab_set()
            tk.Label(
                top,
                text='Saved to config/gui_chat_fonts.json. Menu bar font updates after restart (Tk).',
                wraplength=480,
                justify='left',
            ).pack(anchor='w', padx=10, pady=(10, 6))
            fp = dict(self._font_prefs)
            rows = [
                ('chat_family', 'chat_size', 'Log / chat'),
                ('input_family', 'input_size', 'Command line'),
                ('suggestions_family', 'suggestions_size', 'Suggestions'),
                ('status_family', 'status_size', 'Status bar'),
                ('menu_family', 'menu_size', 'Menus'),
            ]
            frm = tk.Frame(top)
            frm.pack(fill='both', padx=10, pady=4)
            entries = {}
            for i, (fk, sk, lab) in enumerate(rows):
                tk.Label(frm, text=f'{lab}:').grid(row=i, column=0, sticky='w', pady=4)
                ef = tk.Entry(frm, width=24)
                ef.insert(0, str(fp.get(fk, '')))
                ef.grid(row=i, column=1, padx=6)
                sv = tk.StringVar(value=str(int(fp.get(sk, 10))))
                sp = tk.Spinbox(frm, from_=6, to=48, textvariable=sv, width=5)
                sp.grid(row=i, column=2, sticky='w')
                tk.Label(frm, text='pt').grid(row=i, column=3, sticky='w')
                entries[(fk, sk)] = (ef, sv)

            btnf = tk.Frame(top)
            btnf.pack(pady=10)

            def on_ok():
                newp = dict(DEFAULT_GUI_FONT_PREFS)
                for fk, sk, _lab in rows:
                    fam = entries[(fk, sk)][0].get().strip()
                    if not fam:
                        messagebox.showwarning('Font settings', 'Every font family must be non-empty.', parent=top)
                        return
                    try:
                        size = int(entries[(fk, sk)][1].get())
                    except ValueError:
                        messagebox.showwarning('Font settings', 'Invalid point size.', parent=top)
                        return
                    newp[fk] = fam
                    newp[sk] = max(6, min(48, size))
                self._font_prefs = newp
                self._tk_menu_font = (newp['menu_family'], newp['menu_size'])
                save_gui_font_preferences(newp)
                self._apply_font_preferences_tk()
                top.destroy()

            tk.Button(btnf, text='OK', command=on_ok).pack(side='left', padx=4)
            tk.Button(btnf, text='Cancel', command=top.destroy).pack(side='left', padx=4)

        def _handle_rag_mode_capture(self, raw_text: str) -> None:
            cfg = self.registry.config_manager.config or {}
            outcome = capture_rag_sequence_from_input(raw_text, cfg)
            if outcome.error:
                self._append_error(f"RAG capture: {outcome.error}\n\n")
                return
            safe, err = validate_llm_commands(outcome.commands, self.parser)
            if err:
                self._append_error(f"{err}\n\n")
                return
            tag_note = outcome.tag or "(no tag)"
            rel = outcome.saved_path.name if outcome.saved_path else "?"
            self._append_text(
                f"RAG sequence saved ({rel}) — tag: {tag_note}. "
                f"{len(safe)} command(s) will run.\n"
            )
            if self._sequence_recording:
                self._sequence_record_buffer.extend(safe)
            self._start_command_sequence(safe, origin="user")

        def _handle_rag_command(self, kind: str, query: str) -> None:
            cfg = self.registry.config_manager.config or {}
            if kind == "status":
                self._append_rag_status(cfg)
                return
            if kind == "reload":
                try:
                    idx = reload_index(cfg)
                except Exception as exc:
                    self._append_error(f"RAG reload failed: {exc}\n\n")
                    return
                if idx is None:
                    self._append_error("RAG is disabled or the docs folder is missing.\n\n")
                    return
                self._append_text(
                    f"RAG reloaded: {idx.file_count} files, {idx.chunk_count} chunks.\n\n"
                )
                return
            if kind == "query":
                try:
                    _block, hits = retrieve_for_prompt(query, cfg)
                except Exception as exc:
                    self._append_error(f"RAG query failed: {exc}\n\n")
                    return
                if not hits:
                    self._append_text("(No matching RAG chunks.)\n\n")
                    return
                self._append_text(f"RAG matches for {query!r}:\n")
                for i, h in enumerate(hits, 1):
                    self._append_text(
                        f"  [{i}] {h.rel_path}#chunk{h.chunk_index}  score={h.score:.2f}\n      {h.snippet}\n"
                    )
                self._append_text("\n")

        def _append_rag_status(self, cfg) -> None:
            try:
                info = index_status(cfg)
            except Exception as exc:
                self._append_error(f"RAG status failed: {exc}\n\n")
                return
            self._append_text(
                "RAG status:\n"
                f"  enabled : {info.get('enabled')}\n"
                f"  folder  : {info.get('dir')}\n"
                f"  exists  : {info.get('exists')}\n"
                f"  files   : {info.get('files')}\n"
                f"  chunks  : {info.get('chunks')}\n"
                f"  top_k   : {info.get('top_k')}\n"
                f"  exts    : {', '.join(info.get('extensions') or [])}\n\n"
            )

        def show_help(self):
            response = handle_help([], self.registry)
            self._append_text(f'\n{response}\n\n')

    def main():
        windows_set_app_user_model_id()
        window = ChatWindow()
        window.root.mainloop()
except ImportError:
    def main():
        print('Error: GUI dependencies are not installed.')
        print('Install either PyQt5 or use a Python environment with tkinter available.')
        sys.exit(1)

