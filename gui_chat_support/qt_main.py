"""PyQt5 Lab Automation Chat window and entrypoint."""

import json
import os
import re
import sys
import threading
from datetime import datetime
from functools import partial
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QListWidget,
    QFileDialog,
    QStatusBar,
    QDialog,
    QLabel,
    QComboBox,
    QFormLayout,
    QLineEdit,
    QCheckBox,
    QSpinBox,
    QMessageBox,
    QDialogButtonBox,
    QStyleFactory,
    QStackedWidget,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, QEvent, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QColor, QFont, QGuiApplication, QIcon, QImage, QTextCursor, QTextCharFormat

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
from gui_chat_support.command_completer import CommandCompleter
from gui_chat_support.run_command import run_chat_command

_REPO_FILE = str(Path(__file__).resolve().parent.parent / "gui_chat.py")


_LAB_CHAT_MAIN_QSS = """
    QMainWindow { background-color: #e9ecef; }
    QMenuBar {
        background-color: #ffffff;
        border-bottom: 1px solid #dee2e6;
        padding: 3px 6px;
    }
    QMenuBar::item { padding: 5px 12px; border-radius: 4px; }
    QMenuBar::item:selected { background-color: #e7f1ff; }
    QMenuBar::item:pressed { background-color: #cfe2ff; }
    QStatusBar {
        background-color: #ffffff;
        border-top: 1px solid #dee2e6;
        color: #495057;
        padding: 3px 10px;
    }
    QTextEdit#chatDisplay {
        background-color: #ffffff;
        color: #212529;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        padding: 12px 14px;
        selection-background-color: #0d6efd;
        selection-color: #ffffff;
    }
    QTextEdit#inputLine {
        background-color: #ffffff;
        color: #212529;
        border: 1px solid #adb5bd;
        border-radius: 8px;
        padding: 10px 12px;
        selection-background-color: #0d6efd;
        selection-color: #ffffff;
    }
    QTextEdit#inputLine:focus { border: 1px solid #0d6efd; }
    QListWidget#suggestionsList {
        background-color: #ffffff;
        color: #212529;
        border: 1px solid #dee2e6;
        border-radius: 6px;
        padding: 4px;
    }
    QListWidget#suggestionsList::item { padding: 6px 8px; border-radius: 4px; }
    QListWidget#suggestionsList::item:selected { background-color: #e7f1ff; color: #084298; }
    QListWidget#suggestionsList::item:hover { background-color: #f1f3f5; }
    QPushButton#secondaryClearButton {
        min-width: 80px;
        max-width: 80px;
        min-height: 40px;
        max-height: 40px;
        background-color: #ffffff;
        color: #495057;
        border: 1px solid #ced4da;
        border-radius: 10px;
        font-family: "Segoe UI", "Arial", sans-serif;
        font-size: 12px;
        font-weight: 500;
    }
    QPushButton#secondaryClearButton:hover { background-color: #f8f9fa; border-color: #adb5bd; }
    QPushButton#secondaryClearButton:pressed { background-color: #e9ecef; }
"""

_LAB_CHAT_SEND_QSS = """
    QPushButton#primarySendButton {
        min-width: 80px;
        max-width: 80px;
        min-height: 40px;
        max-height: 40px;
        background-color: #0d6efd;
        color: #ffffff;
        border: none;
        border-radius: 10px;
        font-family: "Segoe UI", "Arial", sans-serif;
        font-size: 13px;
        font-weight: 600;
    }
    QPushButton#primarySendButton:hover { background-color: #0b5ed7; }
    QPushButton#primarySendButton:pressed { background-color: #0a58ca; }
"""

_LAB_CHAT_STOP_QSS = """
    QPushButton#primarySendButton {
        min-width: 80px;
        max-width: 80px;
        min-height: 40px;
        max-height: 40px;
        background-color: #dc3545;
        color: #ffffff;
        border: none;
        border-radius: 10px;
        font-family: "Segoe UI", "Arial", sans-serif;
        font-size: 13px;
        font-weight: 600;
    }
    QPushButton#primarySendButton:hover { background-color: #bb2d3b; }
    QPushButton#primarySendButton:pressed { background-color: #a52834; }
"""

class ChatWindow(QMainWindow, AutomationLoopMixin):
    # Queued delivery from LLM worker thread → GUI thread (do not use QTimer from background threads).
    _llm_plan_ok = pyqtSignal(object, object)
    _llm_plan_err = pyqtSignal(str)
    _llm_analysis_ok = pyqtSignal(str, object)
    _llm_analysis_err = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._llm_plan_ok.connect(self._on_llm_plan_ok)
        self._llm_plan_err.connect(self._on_llm_plan_err)
        self._llm_analysis_ok.connect(self._on_llm_analysis_ok)
        self._llm_analysis_err.connect(self._on_llm_analysis_err)
        self.setWindowTitle('Lab Automation Chat')
        # Size window to ~75% of available screen
        try:
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                w = int(geo.width() * 0.75)
                h = int(geo.height() * 0.75)
                x = geo.x() + int((geo.width() - w) / 2)
                y = geo.y() + int((geo.height() - h) / 2)
                self.setGeometry(x, y, w, h)
            else:
                self.setGeometry(100, 100, 1000, 750)
        except Exception:
            self.setGeometry(100, 100, 1000, 750)

        file_menu = self.menuBar().addMenu('File')
        save_action = file_menu.addAction('Save Log')
        save_action.triggered.connect(self.save_log)
        load_action = file_menu.addAction('Load Config')
        load_action.triggered.connect(self.load_config)
        exit_action = file_menu.addAction('Exit')
        exit_action.triggered.connect(self.close)

        scripts_menu = self.menuBar().addMenu('Scripts')
        load_script_action = scripts_menu.addAction('Load Script')
        load_script_action.triggered.connect(self.load_script)

        sequence_menu = self.menuBar().addMenu('Sequence')
        sequence_menu.addAction('Start').triggered.connect(self._sequence_recording_start)
        sequence_menu.addAction('Stop').triggered.connect(self._sequence_recording_stop)
        sequence_menu.addAction('Remove test sequence...').triggered.connect(self._remove_test_sequence_dialog)

        self.test_sequence_menu = self.menuBar().addMenu('Test Sequence')

        bench_menu = self.menuBar().addMenu('Bench')
        bench_menu.addAction('Discover devices…').triggered.connect(self._discover_devices_dialog)
        bench_menu.addAction('Bind instrument…').triggered.connect(self._open_bind_instrument_dialog)

        settings_menu = self.menuBar().addMenu('Settings')
        settings_action = settings_menu.addAction('Bench Settings')
        settings_action.triggered.connect(self.open_bench_settings)
        llm_action = settings_menu.addAction('LLM settings…')
        llm_action.triggered.connect(self.open_llm_settings)
        fonts_action = settings_menu.addAction('Fonts…')
        fonts_action.triggered.connect(self.open_font_settings)

        help_menu = self.menuBar().addMenu('Help')
        show_help_action = help_menu.addAction('Show Commands')
        show_help_action.triggered.connect(self.show_help)

        central_widget = QWidget()
        central_widget.setObjectName('centralRoot')
        self.layout = QVBoxLayout(central_widget)
        self.layout.setContentsMargins(14, 14, 14, 14)
        self.layout.setSpacing(12)

        self.chat_display = QTextEdit()
        self.chat_display.setObjectName('chatDisplay')
        self.chat_display.setReadOnly(True)
        self.layout.addWidget(self.chat_display, 1)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(QLabel('LLM chat mode:'))
        self._chat_mode_combo = QComboBox()
        self._chat_mode_combo.addItems(['Agent', 'Plan'])
        self._chat_mode_combo.setToolTip(
            'Agent: run generated bench/bc commands immediately. '
            'Plan: show the proposed list first — type run or go to execute, or discard to cancel.'
        )
        self._chat_mode_combo.currentIndexChanged.connect(self._on_chat_mode_combo_changed)
        mode_row.addWidget(self._chat_mode_combo, 0)
        mode_row.addStretch(1)
        self.layout.addLayout(mode_row)

        composer_row = QHBoxLayout()
        composer_row.setSpacing(10)

        self.input_line = QTextEdit()
        self.input_line.setObjectName('inputLine')
        self.input_line.setAcceptRichText(False)
        self.input_line.setFixedHeight(92)
        self.input_line.installEventFilter(self)
        self.input_line.textChanged.connect(self.on_input_changed)
        self.input_line.setPlaceholderText(
            'Command line — bench. / bc. commands; use ; or newline between steps. Shift+Enter for newline.'
        )
        composer_row.addWidget(self.input_line, 1)

        action_col = QVBoxLayout()
        action_col.setSpacing(8)
        action_col.addStretch(1)

        self.clear_button = QPushButton('Clear')
        self.clear_button.setObjectName('secondaryClearButton')
        self.clear_button.setToolTip('Clear log view')
        self.clear_button.clicked.connect(self.clear_screen)
        action_col.addWidget(self.clear_button, 0, Qt.AlignHCenter)

        self.send_button = QPushButton('Send')
        self.send_button.setObjectName('primarySendButton')
        self.send_button.setToolTip('Run command (Enter)')
        self.send_button.setStyleSheet(_LAB_CHAT_SEND_QSS)
        self.send_button.clicked.connect(self._on_send_or_stop_clicked)
        action_col.addWidget(self.send_button, 0, Qt.AlignHCenter)

        composer_row.addLayout(action_col)

        self.layout.addLayout(composer_row)

        self.suggestions_list = QListWidget()
        self.suggestions_list.setObjectName('suggestionsList')
        self.suggestions_list.setMaximumHeight(140)
        self.suggestions_list.setUniformItemSizes(True)
        self.suggestions_list.itemClicked.connect(self.on_suggestion_clicked)
        self.layout.addWidget(self.suggestions_list)
        self.suggestions_list.hide()

        self.setCentralWidget(central_widget)
        self.setStyleSheet(_LAB_CHAT_MAIN_QSS)

        self.parser = CommandParser()
        self.registry = CommandRegistry()
        self.completer = CommandCompleter(self.registry)

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
        self._delay_timer = QTimer(self)
        self._delay_timer.setSingleShot(True)
        self._delay_timer.timeout.connect(self._on_delay_timer_done)
        self._init_automation_loop()
        self._llm_plan_ok_repair = False

        self.status_bar = self.statusBar()
        self._font_prefs = load_gui_font_preferences()
        self._apply_widget_fonts()
        self._apply_menu_fonts()
        self.update_status_bar()

        self._append_text('Lab Automation Chat\n')
        self._append_text("Type 'help' for available commands\n")
        self._append_text("Type 'bench.' or 'bc.' to see command suggestions\n")
        self._append_text("Use semicolons or Shift+Enter for multiple commands.\n")
        self._append_text("Use bench.config.* to manage real/sim mode and discovery.\n")
        self._append_text("Use bench.<inst>.raw <SCPI> for raw instrument commands in real mode.\n")
        self._append_text(
            "Plot: plot bc.sg.measure frequency — scalar; 1D/2D series go to logs/plot_data/*.csv "
            '(optional name: plot "Test Data" bc.osc.get_trace 1); '
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
        self._append_text("History: Up/Down recalls last commands (when suggestions are hidden).\n")
        self._append_text('Section heading: wrap the title in double quotes, e.g. "Power Cycle Test".\n')
        self._append_text('Delay: use delay 10 to wait 10 seconds before the next command; Send becomes Stop.\n')
        self._append_text(
            'Sequence menu: Start records commands; Stop asks for category and name; '
            'Remove deletes a saved sequence. Saved items appear under Test Sequence by category.\n'
        )
        self._append_text('=' * 60 + '\n\n')

        self._rebuild_test_sequence_menu()

        self._apply_chat_mode_from_config()
        self._sync_chat_mode_combo()

    def _apply_chat_mode_from_config(self) -> None:
        llm = self.registry.config_manager.config.get('llm') or {}
        if not isinstance(llm, dict):
            llm = {}
        self._chat_mode = normalize_chat_mode(llm.get('chat_mode'))

    def _sync_chat_mode_combo(self) -> None:
        idx = 1 if self._chat_mode == CHAT_MODE_PLAN else 0
        self._chat_mode_combo.blockSignals(True)
        self._chat_mode_combo.setCurrentIndex(idx)
        self._chat_mode_combo.blockSignals(False)

    def _on_chat_mode_combo_changed(self, index: int) -> None:
        self._chat_mode = CHAT_MODE_PLAN if int(index) == 1 else CHAT_MODE_AGENT
        self.update_status_bar()

    def _clear_pending_plan(self) -> None:
        self._pending_plan_commands = None
        self._pending_plan_user_text = ""

    def _apply_widget_fonts(self) -> None:
        p = self._font_prefs
        self.chat_display.setFont(QFont(p['chat_family'], p['chat_size']))
        self.input_line.setFont(QFont(p['input_family'], p['input_size']))
        self.suggestions_list.setFont(QFont(p['suggestions_family'], p['suggestions_size']))
        self.status_bar.setFont(QFont(p['status_family'], p['status_size']))

    def _apply_menu_fonts(self) -> None:
        p = self._font_prefs
        mf = QFont(p['menu_family'], p['menu_size'])
        self.menuBar().setFont(mf)

        def walk_menu(menu) -> None:
            menu.setFont(mf)
            for act in menu.actions():
                if act.menu():
                    walk_menu(act.menu())

        for act in self.menuBar().actions():
            if act.menu():
                walk_menu(act.menu())

    def _apply_font_preferences(self) -> None:
        self._apply_widget_fonts()
        self._apply_menu_fonts()

    def open_font_settings(self) -> None:
        p = dict(self._font_prefs)
        d = QDialog(self)
        d.setWindowTitle('Font settings')
        d.setModal(True)
        d.resize(520, 340)
        layout = QVBoxLayout(d)
        layout.addWidget(
            QLabel('Font family and size (points). Saved to config/gui_chat_fonts.json')
        )
        form = QFormLayout()
        rows = [
            ('chat_family', 'chat_size', 'Log / chat'),
            ('input_family', 'input_size', 'Command line'),
            ('suggestions_family', 'suggestions_size', 'Suggestions'),
            ('status_family', 'status_size', 'Status bar'),
            ('menu_family', 'menu_size', 'Menus'),
        ]
        edits: dict = {}
        for fk, sk, label in rows:
            row_w = QWidget()
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 0, 0, 0)
            fe = QLineEdit()
            fe.setText(str(p.get(fk, '')))
            sz = QSpinBox()
            sz.setRange(6, 48)
            sz.setValue(int(p.get(sk, 10)))
            row.addWidget(fe, 1)
            row.addWidget(QLabel('pt'))
            row.addWidget(sz)
            form.addRow(label + ':', row_w)
            edits[fk] = fe
            edits[sk] = sz
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)

        def on_ok() -> None:
            newp = dict(DEFAULT_GUI_FONT_PREFS)
            for fk, sk, _lbl in [
                ('chat_family', 'chat_size', ''),
                ('input_family', 'input_size', ''),
                ('suggestions_family', 'suggestions_size', ''),
                ('status_family', 'status_size', ''),
                ('menu_family', 'menu_size', ''),
            ]:
                fam = edits[fk].text().strip()
                if not fam:
                    QMessageBox.warning(d, 'Font settings', f'Family for {fk} cannot be empty.')
                    return
                newp[fk] = fam
                newp[sk] = int(edits[sk].value())
            self._font_prefs = newp
            save_gui_font_preferences(newp)
            self._apply_font_preferences()
            d.accept()

        buttons.accepted.connect(on_ok)
        buttons.rejected.connect(d.reject)
        d.exec_()

    def _rebuild_test_sequence_menu(self) -> None:
        self.test_sequence_menu.clear()
        examples_menu = self.test_sequence_menu.addMenu('Examples')
        ex = examples_menu.addAction('Power cycle (1s on/off)')
        ex.triggered.connect(partial(self._run_stored_command_list, list(EXAMPLE_POWER_CYCLE_COMMANDS)))
        cats = self._test_sequences.get('categories') or {}
        for cat in sorted(cats.keys()):
            sub = self.test_sequence_menu.addMenu(cat)
            for name in sorted((cats[cat] or {}).keys()):
                act = sub.addAction(name)
                act.triggered.connect(partial(self._run_named_sequence, cat, name))
        self._apply_menu_fonts()

    def _run_stored_command_list(self, commands: list) -> None:
        if self._sequence_active:
            QMessageBox.warning(self, 'Sequence running', 'Stop the current sequence before starting another.')
            return
        self._start_command_sequence(list(commands), origin="user")

    def _run_named_sequence(self, category: str, name: str) -> None:
        cmds = ((self._test_sequences.get('categories') or {}).get(category) or {}).get(name)
        if not cmds:
            QMessageBox.warning(
                'Missing sequence', f'No saved commands for {category!r} / {name!r}.'
            )
            return
        self._run_stored_command_list(list(cmds))

    def _prompt_category_and_name(self, title: str) -> tuple:
        """Return (category, name) stripped, or (None, None) if cancelled."""
        d = QDialog(self)
        d.setWindowTitle(title)
        d._saved_cat = ''
        d._saved_name = ''
        layout = QVBoxLayout(d)
        form = QFormLayout()
        cat_edit = QLineEdit()
        cat_edit.setPlaceholderText('e.g. power_cycle, thermal, bringup')
        name_edit = QLineEdit()
        name_edit.setPlaceholderText('e.g. smoke A, overnight soak')
        form.addRow('Category', cat_edit)
        form.addRow('Name', name_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)

        def on_ok() -> None:
            cat = cat_edit.text().strip()
            name = name_edit.text().strip()
            if not cat or not name:
                QMessageBox.warning(d, title, 'Category and name must both be non-empty.')
                return
            d._saved_cat = cat
            d._saved_name = name
            d.accept()

        buttons.accepted.connect(on_ok)
        buttons.rejected.connect(d.reject)
        if d.exec_() != QDialog.Accepted:
            return None, None
        return d._saved_cat, d._saved_name

    def _remove_test_sequence_dialog(self) -> None:
        cats = self._test_sequences.get('categories') or {}
        flat = [(c, n) for c in sorted(cats) for n in sorted((cats.get(c) or {}).keys())]
        if not flat:
            QMessageBox.information(self, 'Remove test sequence', 'No saved test sequences to remove.')
            return
        d = QDialog(self)
        d.setWindowTitle('Remove test sequence')
        layout = QVBoxLayout(d)
        layout.addWidget(QLabel('Select a sequence to remove:'))
        lw = QListWidget()
        for c, n in flat:
            lw.addItem(f'{c} → {n}')
        lw.setCurrentRow(0)
        layout.addWidget(lw)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(d.accept)
        buttons.rejected.connect(d.reject)
        if d.exec_() != QDialog.Accepted:
            return
        row = lw.currentRow()
        if row < 0:
            QMessageBox.warning(self, 'Remove test sequence', 'Select an entry in the list.')
            return
        category, name = flat[row]
        reply = QMessageBox.question(
            self,
            'Confirm remove',
            f'Remove sequence {category!r} / {name!r}?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        cat_map = self._test_sequences.setdefault('categories', {})
        if category in cat_map and name in cat_map[category]:
            del cat_map[category][name]
            if not cat_map[category]:
                del cat_map[category]
        try:
            save_test_sequences(self._test_sequences)
        except OSError as e:
            QMessageBox.critical(self, 'Save failed', str(e))
            return
        self._rebuild_test_sequence_menu()
        self._append_text(f'Removed test sequence {category!r} / {name!r}.\n\n')

    def _sequence_recording_start(self) -> None:
        if self._sequence_active:
            QMessageBox.warning(self, 'Sequence running', 'Stop the running sequence before starting recording.')
            return
        self._sequence_recording = True
        self._sequence_record_buffer = []
        self._append_text(f'[{self._timestamp()}] Sequence recording started. Send commands; use Sequence → Stop to save.\n\n')

    def _sequence_recording_stop(self) -> None:
        if not self._sequence_recording:
            QMessageBox.information(self, 'Sequence', 'Recording is not active. Choose Sequence → Start first.')
            return
        self._sequence_recording = False
        if not self._sequence_record_buffer:
            QMessageBox.warning(self, 'Save test sequence', 'Nothing was recorded. Use Start, then send at least one command.')
            self._sequence_record_buffer = []
            return
        category, name = self._prompt_category_and_name('Save test sequence')
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
            QMessageBox.critical(self, 'Save failed', str(e))
            self._sequence_record_buffer = []
            return
        self._sequence_record_buffer = []
        self._rebuild_test_sequence_menu()
        self._append_text(
            f'Saved test sequence {name!r} under category {category!r} (Test Sequence → {category}).\n\n'
        )

    def _set_run_button_sequence_mode(self, running: bool) -> None:
        if running:
            self.send_button.setText('Stop')
            self.send_button.setToolTip('Stop running sequence')
            self.send_button.setStyleSheet(_LAB_CHAT_STOP_QSS)
        else:
            self.send_button.setText('Send')
            self.send_button.setToolTip('Run command (Enter)')
            self.send_button.setStyleSheet(_LAB_CHAT_SEND_QSS)

    def _on_send_or_stop_clicked(self) -> None:
        if self._sequence_active:
            self._delay_timer.stop()
            self._sequence_stopped_by_user = True
            self._append_text('Sequence stopped.\n\n')
            self._finish_sequence()
        else:
            self.send_command()

    def _finish_sequence(self) -> None:
        self._delay_timer.stop()
        self._sequence_active = False
        self._sequence_queue = []
        self._sequence_index = 0
        self._set_run_button_sequence_mode(False)
        self.update_status_bar()
        if self._sequence_results:
            self._last_results = list(self._sequence_results)
            self._last_results_user_text = self._sequence_user_text
        if self._finish_sequence_automation_hook():
            return
        self._maybe_run_post_analysis()

    def _emit_llm_plan_ok(self, commands, analysis, repair: bool = False) -> None:
        self._llm_plan_ok_repair = bool(repair)
        self._llm_plan_ok.emit(commands, analysis)

    def _emit_llm_plan_err(self, msg: str) -> None:
        self._llm_plan_err.emit(msg)

    def _on_delay_timer_done(self) -> None:
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
                self._llm_analysis_err.emit(f"LLM analysis error: {e}")
                return
            self._llm_analysis_ok.emit(analysis or "", plot_spec)

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
                self._llm_analysis_err.emit(f"LLM analysis error: {e}")
                return
            self._llm_analysis_ok.emit(analysis or "", plot_spec)

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
                QTimer.singleShot(0, self._run_next_sequence_step)
                return
            try:
                sec = float(parts[1].strip())
            except ValueError:
                self._append_error(f'Invalid delay value: {parts[1]!r}\n\n')
                QTimer.singleShot(0, self._run_next_sequence_step)
                return
            if sec < 0:
                self._append_error('Delay must be non-negative.\n\n')
                QTimer.singleShot(0, self._run_next_sequence_step)
                return
            ms = int(min(sec * 1000.0, 86400000))
            ms = max(ms, 0)
            self._delay_timer.start(ms)
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
        QTimer.singleShot(0, self._run_next_sequence_step)

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
            self.input_line.setPlainText(text)
            cursor = self.input_line.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.input_line.setTextCursor(cursor)
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

    def _reload_after_config_change(self, source_label: str) -> None:
        self.registry.reload_instruments()
        self.completer = CommandCompleter(self.registry)
        self._apply_chat_mode_from_config()
        self._sync_chat_mode_combo()
        self.update_status_bar()
        self.on_input_changed()
        self._append_text(f'{source_label}\n\n')

    def _get_last_fragment(self, text: str) -> str:
        return re.split(r'[;\n\r]+', text)[-1].strip()

    def _apply_suggestion(self, suggestion: str) -> None:
        """Replace only the last command fragment with the suggestion."""
        suggestion = (suggestion or "").strip()
        if not suggestion:
            return

        text = self.input_line.toPlainText()
        parts = re.split(r'([;\n\r]+)', text)
        if not parts:
            self.input_line.setPlainText(suggestion)
        else:
            if len(parts) == 1:
                parts[0] = suggestion
            else:
                parts[-1] = suggestion
            self.input_line.setPlainText(''.join(parts))

        cursor = self.input_line.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.input_line.setTextCursor(cursor)
        self.input_line.setFocus()
        self.suggestions_list.hide()
        self._history_browse_index = None

    def eventFilter(self, obj, event):
        if obj is self.input_line and event.type() == QEvent.KeyPress:
            if event.key() in {Qt.Key_Return, Qt.Key_Enter}:
                if self._sequence_active and not (event.modifiers() & Qt.ShiftModifier):
                    return True
            if event.key() in {Qt.Key_Up, Qt.Key_Down} and self.suggestions_list.isVisible():
                count = self.suggestions_list.count()
                if count > 0:
                    current = self.suggestions_list.currentRow()
                    if current < 0:
                        current = 0 if event.key() == Qt.Key_Down else count - 1
                    else:
                        if event.key() == Qt.Key_Down:
                            current = (current + 1) % count
                        else:
                            current = (current - 1 + count) % count
                    self.suggestions_list.setCurrentRow(current)
                    return True

            if event.key() == Qt.Key_Up:
                self._history_up()
                return True
            if event.key() == Qt.Key_Down:
                self._history_down()
                return True

            if event.key() == Qt.Key_Tab and self.suggestions_list.isVisible():
                item = self.suggestions_list.currentItem()
                if item is not None:
                    self._apply_suggestion(item.text())
                    return True

            if event.key() in {Qt.Key_Return, Qt.Key_Enter}:
                if event.modifiers() & Qt.ShiftModifier:
                    return False
                if self.suggestions_list.isVisible() and self.suggestions_list.currentItem() is not None:
                    self._apply_suggestion(self.suggestions_list.currentItem().text())
                    return True
                self.send_command()
                return True
        return super().eventFilter(obj, event)

    def on_input_changed(self):
        if not self._history_setting_text:
            self._history_browse_index = None
        text = self.input_line.toPlainText().strip()
        last_fragment = self._get_last_fragment(text)
        if last_fragment.startswith(('bench.', 'bc.')):
            suggestions = self.completer.get_suggestions(text)
            self._update_suggestions(suggestions)
        else:
            self.suggestions_list.hide()

    def _update_suggestions(self, suggestions):
        self.suggestions_list.clear()
        if suggestions:
            for suggestion in suggestions:
                self.suggestions_list.addItem(suggestion)
            self.suggestions_list.show()
            if self.suggestions_list.currentRow() < 0 and self.suggestions_list.count() > 0:
                self.suggestions_list.setCurrentRow(0)
        else:
            self.suggestions_list.hide()

    def on_suggestion_clicked(self, item):
        self._apply_suggestion(item.text())

    def _on_llm_plan_err(self, msg: str) -> None:
        self._append_error(f"{msg}\n\n")

    def _on_llm_plan_ok(self, commands, analysis) -> None:
        repair = bool(getattr(self, "_llm_plan_ok_repair", False))
        self._llm_plan_ok_repair = False
        self._on_llm_plan_ok_automation(commands, analysis, repair=repair)

    def send_command(self):
        if self._sequence_active:
            return
        raw_text = self.input_line.toPlainText().strip()
        if not raw_text:
            return

        pa = parse_plan_action(raw_text)
        if self._pending_plan_commands is not None and pa is not None:
            self.suggestions_list.hide()
            self._history_append(raw_text)
            self._history_browse_index = None
            self.input_line.clear()
            self.update_status_bar()
            self._append_text(f'[{self._timestamp()}] You: {raw_text}\n')
            cmds = self._pending_plan_commands
            ut = self._pending_plan_user_text
            self._clear_pending_plan()
            if pa == "run":
                self._store_loop_commands(cmds)
                if self._sequence_recording:
                    self._sequence_record_buffer.extend(cmds)
                self.update_status_bar()
                self._start_command_sequence(cmds, origin="llm", user_text=ut)
            else:
                self._append_text("Plan discarded.\n\n")
                self.update_status_bar()
            return

        if self._pending_plan_commands is not None:
            if looks_like_direct_command(raw_text):
                self._clear_pending_plan()
                self._append_text("(Pending plan cleared — running direct commands.)\n\n")
            elif not looks_like_direct_command(raw_text):
                self._clear_pending_plan()
                self._append_text("(Previous plan discarded.)\n\n")

        self.suggestions_list.hide()
        self._history_append(raw_text)
        self._history_browse_index = None
        self.input_line.clear()
        self.update_status_bar()

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

    def _default_char_format(self) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor('#212529'))
        return fmt

    def _append_text(self, text: str):
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.setCharFormat(self._default_char_format())
        cursor.insertText(text)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()

    def _append_heading(self, title: str) -> None:
        title = (title or "").strip()
        if not title:
            return
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        hf = QTextCharFormat()
        f = QFont(self.chat_display.font())
        f.setBold(True)
        f.setUnderline(True)
        pt = f.pointSize()
        if pt <= 0:
            pt = self.chat_display.fontInfo().pointSize() or 10
        f.setPointSize(pt + 2)
        hf.setFont(f)
        hf.setForeground(QColor('#0c4a6e'))
        cursor.setCharFormat(hf)
        cursor.insertText(title + "\n")
        cursor.setCharFormat(self._default_char_format())
        line = "─" * min(72, max(24, len(title)))
        cursor.insertText(line + "\n\n")
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()

    def clear_screen(self):
        self.chat_display.clear()

    def _timestamp(self) -> str:
        return datetime.now().strftime('%H:%M:%S')

    def _append_error(self, text: str):
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        char_format = QTextCharFormat()
        char_format.setForeground(QColor('#c92a2a'))
        cursor.insertText(text, char_format)
        cursor.setCharFormat(self._default_char_format())
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()

    def _append_plot_from_data(self, data):
        try:
            png = render_plot_to_png_bytes(data)
        except Exception as e:
            self._append_error(f'Plot error: {e}\n\n')
            return
        qimg = QImage.fromData(png)
        if qimg.isNull():
            self._append_error('Plot error: could not load image\n\n')
            return
        max_w = max(320, min(720, self.chat_display.width() - 40))
        if qimg.width() > max_w:
            qimg = qimg.scaledToWidth(max_w, Qt.SmoothTransformation)
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertImage(qimg)
        cursor.setCharFormat(self._default_char_format())
        cursor.insertText('\n')
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()

    def update_status_bar(self):
        simulate_dict = self.registry.config_manager.config.get('simulate', {})
        simulate_values = list(simulate_dict.values())
        if all(s for s in simulate_values):
            mode = "Simulated"
        elif not any(s for s in simulate_values):
            mode = "Real"
        else:
            mode = "Mixed"
        instruments = ", ".join(sorted([k for k in self.registry.instruments.keys() if k != 'config']))
        chat_label = "Plan" if self._chat_mode == CHAT_MODE_PLAN else "Agent"
        pending = " | Plan pending" if self._pending_plan_commands else ""
        self.status_bar.showMessage(
            f"Mode: {mode} | Instruments: {instruments} | LLM chat: {chat_label}{pending}"
        )

    def _discover_devices_dialog(self) -> None:
        """Run VISA/serial discovery off the UI thread and show results."""
        self._append_text('Discovering devices (background)…\n')

        def _bg():
            try:
                devices = self.registry.config_manager.discover_available_devices()
            except Exception as e:
                self._append_error(f'Discovery error: {e}\n\n')
                return
            lines = ['Device discovery results:']
            for section, entries in devices.items():
                lines.append(f'  {section}:')
                if not entries:
                    lines.append('    (none)')
                else:
                    for entry in entries:
                        lines.append(f'    {entry}')
            self._append_text('\n'.join(lines) + '\n\n')

        threading.Thread(target=_bg, daemon=True).start()

    def _open_bind_instrument_dialog(self) -> None:
        """Bind a discovered or typed address to an instrument category."""
        dlg = QDialog(self)
        dlg.setWindowTitle('Bind instrument address')
        form = QFormLayout(dlg)

        cat_combo = QComboBox()
        cats = sorted(
            c for c in self.registry.instruments.keys() if c != 'config'
        )
        cat_combo.addItems(cats)

        transport_combo = QComboBox()
        transport_combo.addItems(['visa', 'serial', 'tcp'])

        address_edit = QLineEdit()
        address_edit.setPlaceholderText('e.g. GPIB0::1::INSTR or COM3 or 192.168.1.10:5025')

        discover_btn = QPushButton('Discover…')
        pick_list = QListWidget()
        pick_list.setMaximumHeight(120)

        def _on_discover():
            discover_btn.setEnabled(False)
            pick_list.clear()

            def _bg():
                try:
                    devices = self.registry.config_manager.discover_available_devices()
                except Exception as e:
                    self._append_error(f'Discovery error: {e}\n\n')
                    discover_btn.setEnabled(True)
                    return
                items = []
                for section, entries in devices.items():
                    for entry in entries:
                        items.append(f'{section}: {entry}')
                def _fill():
                    pick_list.addItems(items or ['(no devices found)'])
                    discover_btn.setEnabled(True)
                QTimer.singleShot(0, _fill)

            threading.Thread(target=_bg, daemon=True).start()

        discover_btn.clicked.connect(_on_discover)

        def _on_pick():
            row = pick_list.currentItem()
            if not row:
                return
            text = row.text()
            if ':' in text:
                _, _, rest = text.partition(': ')
                address_edit.setText(rest.strip())
                if text.startswith('serial:'):
                    transport_combo.setCurrentText('serial')
                elif text.startswith('tcp'):
                    transport_combo.setCurrentText('tcp')
                else:
                    transport_combo.setCurrentText('visa')

        pick_list.itemDoubleClicked.connect(lambda _: _on_pick())

        form.addRow('Category', cat_combo)
        form.addRow('Transport', transport_combo)
        form.addRow('Address', address_edit)
        form.addRow(discover_btn, pick_list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)

        if dlg.exec_() != QDialog.Accepted:
            return

        category = cat_combo.currentText().strip()
        transport = transport_combo.currentText().strip()
        address = address_edit.text().strip()
        if not address:
            QMessageBox.warning(self, 'Bind instrument', 'Address is required.')
            return
        try:
            cmd = f'bc.config.bind {category} {transport} {address}'
            parsed = self.parser.parse(cmd)
            if not parsed:
                raise ValueError('Invalid bind command')
            result = self.registry.execute(parsed['category'], parsed['action'], parsed['args'])
            self._reload_after_config_change(str(result))
            self._append_text(f'{result}\n\n')
        except Exception as e:
            QMessageBox.critical(self, 'Bind failed', str(e))

    def save_log(self):
        text = self.chat_display.toPlainText()
        filename, _ = QFileDialog.getSaveFileName(self, 'Save Log', '', 'Text Files (*.txt);;All Files (*)')
        if filename:
            with open(filename, 'w') as f:
                f.write(text)

    def load_config(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            'Load Config',
            CONFIG_DIALOG_START,
            'JSON Files (*.json);;All Files (*)'
        )
        if not filename:
            return

        try:
            self.registry.config_manager.load_config(filename)
            self._reload_after_config_change(f'Loaded config: {filename}')
        except Exception as e:
            self._append_error(f'Error loading config: {e}\n\n')

    def load_script(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            'Load Script',
            '',
            'Script Files (*.txt *.bench *.script *.cmd);;Text Files (*.txt);;All Files (*)'
        )
        if not filename:
            return

        try:
            with open(filename, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            self._history_browse_index = None
            self._history_setting_text = True
            try:
                self.input_line.setPlainText(content.strip())
                cursor = self.input_line.textCursor()
                cursor.movePosition(QTextCursor.End)
                self.input_line.setTextCursor(cursor)
                self.on_input_changed()
            finally:
                self._history_setting_text = False
            self.input_line.setFocus()
            self._append_text(f'Loaded script into command box: {filename}\n\n')
        except Exception as e:
            self._append_error(f'Error loading script: {e}\n\n')

    def open_bench_settings(self):
        cfg_mgr = self.registry.config_manager
        config = cfg_mgr.config or {}
        instruments = (config.get('instruments') or {})
        global_settings = (config.get('global_settings') or {})
        comm = (config.get('communication') or {})
        protocol_choices = comm.get('protocols') or ['VISA', 'TCP/IP', 'Serial', 'USB']

        dialog = QDialog(self)
        dialog.setWindowTitle('Bench Settings')
        dialog.setModal(True)
        dialog.resize(720, 520)

        layout = QVBoxLayout(dialog)
        path = getattr(cfg_mgr, 'config_file', str(default_config_file()))
        layout.addWidget(QLabel(f'Config: {path}'))

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel('Instrument:'))
        instrument_combo = QComboBox()
        instrument_keys = sorted(instruments.keys())
        instrument_combo.addItems(instrument_keys)
        top_row.addWidget(instrument_combo, 1)
        layout.addLayout(top_row)

        form = QFormLayout()
        layout.addLayout(form)

        # Global settings
        g_sim_all = QCheckBox()
        g_sim_all.setChecked(bool(global_settings.get('simulate_all', False)))
        g_auto_connect = QCheckBox()
        g_auto_connect.setChecked(bool(global_settings.get('auto_connect', True)))
        g_enable_cache = QCheckBox()
        g_enable_cache.setChecked(bool(global_settings.get('enable_cache', True)))
        g_conn_timeout = QSpinBox()
        g_conn_timeout.setRange(100, 600000)
        g_conn_timeout.setValue(int(global_settings.get('connection_timeout_ms', 5000) or 5000))
        g_log_level = QComboBox()
        g_log_level.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR'])
        current_level = str(global_settings.get('log_level', 'INFO')).upper()
        idx = g_log_level.findText(current_level)
        if idx >= 0:
            g_log_level.setCurrentIndex(idx)

        form.addRow(QLabel('--- Global Settings ---'), QLabel(''))
        form.addRow('simulate_all', g_sim_all)
        form.addRow('auto_connect', g_auto_connect)
        form.addRow('enable_cache', g_enable_cache)
        form.addRow('connection_timeout_ms', g_conn_timeout)
        form.addRow('log_level', g_log_level)

        # Instrument settings widgets
        form.addRow(QLabel('--- Instrument Settings ---'), QLabel(''))

        i_name = QLineEdit()
        i_type = QLineEdit()
        i_desc = QLineEdit()
        i_sim = QCheckBox()
        i_protocol = QComboBox()
        i_protocol.addItems([str(p) for p in protocol_choices])
        i_visa = QLineEdit()
        i_ip = QLineEdit()
        i_port = QSpinBox()
        i_port.setRange(1, 65535)
        i_timeout = QSpinBox()
        i_timeout.setRange(100, 600000)
        i_serial = QLineEdit()
        i_baud = QSpinBox()
        i_baud.setRange(300, 2000000)
        i_usb = QLineEdit()

        form.addRow('name', i_name)
        form.addRow('type', i_type)
        form.addRow('description', i_desc)
        form.addRow('simulate', i_sim)
        form.addRow('protocol', i_protocol)
        form.addRow('visa_resource', i_visa)
        form.addRow('ip_address', i_ip)
        form.addRow('port', i_port)
        form.addRow('timeout_ms', i_timeout)
        form.addRow('serial_port', i_serial)
        form.addRow('baudrate', i_baud)
        form.addRow('usb_resource', i_usb)

        def load_instrument_fields(key: str) -> None:
            inst = instruments.get(key) or {}
            i_name.setText(str(inst.get('name', '') or ''))
            i_type.setText(str(inst.get('type', '') or ''))
            i_desc.setText(str(inst.get('description', '') or ''))
            i_sim.setChecked(bool(inst.get('simulate', True)))

            proto = inst.get('protocol') or comm.get('default_protocol') or 'VISA'
            pidx = i_protocol.findText(str(proto))
            if pidx >= 0:
                i_protocol.setCurrentIndex(pidx)
            else:
                # allow unseen protocol values
                i_protocol.addItem(str(proto))
                i_protocol.setCurrentIndex(i_protocol.count() - 1)

            i_visa.setText(str(inst.get('visa_resource', '') or ''))
            i_ip.setText(str(inst.get('ip_address', '') or ''))
            i_port.setValue(int(inst.get('port', 5025) or 5025))
            i_timeout.setValue(int(inst.get('timeout_ms', 5000) or 5000))
            i_serial.setText(str(inst.get('serial_port', '') or ''))
            i_baud.setValue(int(inst.get('baudrate', 9600) or 9600))
            i_usb.setText(str(inst.get('usb_resource', '') or ''))

        def save_fields_to_config() -> None:
            # global
            global_settings['simulate_all'] = bool(g_sim_all.isChecked())
            global_settings['auto_connect'] = bool(g_auto_connect.isChecked())
            global_settings['enable_cache'] = bool(g_enable_cache.isChecked())
            global_settings['connection_timeout_ms'] = int(g_conn_timeout.value())
            global_settings['log_level'] = str(g_log_level.currentText())
            config['global_settings'] = global_settings

            # instrument
            key = str(instrument_combo.currentText())
            inst = instruments.get(key) or {}
            inst['name'] = i_name.text().strip()
            inst['type'] = i_type.text().strip()
            inst['description'] = i_desc.text().strip()
            inst['simulate'] = bool(i_sim.isChecked())
            inst['protocol'] = str(i_protocol.currentText()).strip()
            inst['visa_resource'] = i_visa.text().strip()
            inst['ip_address'] = i_ip.text().strip()
            inst['port'] = int(i_port.value())
            inst['timeout_ms'] = int(i_timeout.value())
            inst['serial_port'] = i_serial.text().strip()
            inst['baudrate'] = int(i_baud.value())
            inst['usb_resource'] = i_usb.text().strip()
            instruments[key] = inst
            config['instruments'] = instruments

        def do_save_and_close() -> None:
            try:
                save_fields_to_config()
                cfg_mgr.config = config
                cfg_mgr.save_config()
                cfg_mgr.load_config()
                self._reload_after_config_change('Bench settings saved and reloaded.')
                dialog.accept()
            except Exception as exc:
                QMessageBox.critical(dialog, 'Save failed', str(exc))

        # Buttons
        buttons = QHBoxLayout()
        save_btn = QPushButton('Save')
        close_btn = QPushButton('Close')
        buttons.addWidget(save_btn)
        buttons.addWidget(close_btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        save_btn.clicked.connect(do_save_and_close)
        close_btn.clicked.connect(dialog.reject)

        instrument_combo.currentTextChanged.connect(load_instrument_fields)
        if instrument_keys:
            load_instrument_fields(instrument_keys[0])

        dialog.exec_()

    def open_llm_settings(self) -> None:
        cfg_mgr = self.registry.config_manager
        config = cfg_mgr.config or {}
        llm = (config.get('llm') or {})
        if not isinstance(llm, dict):
            llm = {}
        aoai = (config.get('azure_openai') or {})
        if not isinstance(aoai, dict):
            aoai = {}
        oa = (config.get('openai_api') or {})
        if not isinstance(oa, dict):
            oa = {}
        lg = (config.get('local_gguf') or {})
        if not isinstance(lg, dict):
            lg = {}

        def _timeout_spin_value() -> int:
            for d in (llm, aoai, oa):
                if isinstance(d, dict) and d.get('timeout_seconds') is not None:
                    try:
                        return max(5, min(600, int(float(d['timeout_seconds']))))
                    except (TypeError, ValueError):
                        pass
            return 60

        dialog = QDialog(self)
        dialog.setWindowTitle('LLM settings')
        dialog.setMinimumWidth(820)
        dialog.setModal(True)
        dialog.resize(880, 520)

        layout = QVBoxLayout(dialog)
        path = getattr(cfg_mgr, 'config_file', str(default_config_file()))
        layout.addWidget(QLabel(f'Config: {path}'))
        layout.addWidget(QLabel('Natural-language chat → command generation. Pick provider and credentials.'))

        top_form = QFormLayout()
        layout.addLayout(top_form)

        provider_combo = QComboBox()
        provider_combo.addItems(['Azure OpenAI', 'OpenAI (direct API)', 'Local GGUF (llama.cpp)'])
        _provider_values = [PROVIDER_AZURE, PROVIDER_OPENAI, PROVIDER_LOCAL_GGUF]
        p = str(llm.get('provider', PROVIDER_AZURE) or PROVIDER_AZURE).lower()
        try:
            provider_combo.setCurrentIndex(_provider_values.index(p))
        except ValueError:
            provider_combo.setCurrentIndex(0)

        timeout_s = QSpinBox()
        timeout_s.setRange(5, 600)
        timeout_s.setSuffix(' s')
        timeout_s.setToolTip('Maximum time to wait for the model API (5–600 seconds).')
        timeout_s.setValue(_timeout_spin_value())

        auto_analyze_cb = QCheckBox('Send results back to LLM for analysis and plot')
        auto_analyze_cb.setToolTip(
            'After an LLM-generated sequence finishes, send the captured results back to '
            'the model for a textual analysis and an optional plot rendered inline.'
        )
        _aa_cur = llm.get('auto_analyze_results', True)
        if isinstance(_aa_cur, str):
            _aa_cur = _aa_cur.strip().lower() not in {'false', '0', 'no', 'off'}
        auto_analyze_cb.setChecked(bool(_aa_cur))

        chat_mode_combo = QComboBox()
        chat_mode_combo.addItems(['Agent', 'Plan'])
        cm_cur = normalize_chat_mode(llm.get('chat_mode'))
        chat_mode_combo.setCurrentIndex(1 if cm_cur == CHAT_MODE_PLAN else 0)
        chat_mode_combo.setToolTip(
            'Default for the LLM chat mode control on the main window. '
            'Plan shows proposed commands before execution.'
        )

        loop_cfg = AutomationLoopConfig.from_config(config)
        auto_loop_cb = QCheckBox('Automation loop (auto-repair on FAIL/error)')
        auto_loop_cb.setChecked(loop_cfg.enabled)
        auto_loop_cb.setToolTip(
            'After a failed LLM-driven sequence, ask the model for a minimal repair plan '
            'and re-run (Agent mode runs repairs automatically; Plan mode shows commands first).'
        )
        auto_repair_cb = QCheckBox('Auto-repair on failure')
        auto_repair_cb.setChecked(loop_cfg.auto_repair_on_fail)
        closed_loop_cb = QCheckBox('Closed-loop Agent (auto-run repair steps)')
        closed_loop_cb.setChecked(loop_cfg.closed_loop_agent)
        max_iter_spin = QSpinBox()
        max_iter_spin.setRange(1, 10)
        max_iter_spin.setValue(loop_cfg.max_iterations)
        history_spin = QSpinBox()
        history_spin.setRange(0, 32)
        history_spin.setValue(loop_cfg.multi_turn_history)
        history_spin.setToolTip('Prior user/plan/result turns included in the next LLM request.')

        top_form.addRow('Provider', provider_combo)
        top_form.addRow('Request timeout', timeout_s)
        top_form.addRow('Auto-analyze', auto_analyze_cb)
        top_form.addRow('Default chat mode', chat_mode_combo)
        top_form.addRow('', auto_loop_cb)
        top_form.addRow('Max repair iterations', max_iter_spin)
        top_form.addRow('', auto_repair_cb)
        top_form.addRow('', closed_loop_cb)
        top_form.addRow('Multi-turn history', history_spin)

        stack = QStackedWidget()
        layout.addWidget(stack)

        page_az = QWidget()
        lay_az = QVBoxLayout(page_az)
        form_az = QFormLayout()
        lay_az.addLayout(form_az)
        az_endpoint = QLineEdit(str(aoai.get('endpoint', '') or ''))
        az_deployment = QLineEdit(str(aoai.get('deployment', '') or ''))
        az_api_version = QLineEdit(str(aoai.get('api_version', '2024-02-15-preview') or '2024-02-15-preview'))
        az_api_key = QLineEdit(str(aoai.get('api_key', '') or ''))
        az_api_key.setEchoMode(QLineEdit.Password)
        form_az.addRow('Endpoint', az_endpoint)
        form_az.addRow('Deployment', az_deployment)
        form_az.addRow('API version', az_api_version)
        form_az.addRow('API key', az_api_key)
        stack.addWidget(page_az)

        page_oa = QWidget()
        lay_oa = QVBoxLayout(page_oa)
        form_oa = QFormLayout()
        lay_oa.addLayout(form_oa)
        oa_key = QLineEdit(str(oa.get('api_key', '') or ''))
        oa_key.setEchoMode(QLineEdit.Password)
        oa_model = QLineEdit(str(oa.get('model', '') or 'gpt-4o-mini'))
        oa_base = QLineEdit(str(oa.get('base_url', '') or ''))
        form_oa.addRow('API key', oa_key)
        form_oa.addRow('Model', oa_model)
        form_oa.addRow('Base URL (optional)', oa_base)
        hint_oa = QLabel(
            'Leave base URL empty for the default OpenAI API. Set a URL for OpenAI-compatible proxies.'
        )
        hint_oa.setWordWrap(True)
        lay_oa.addWidget(hint_oa)
        stack.addWidget(page_oa)

        page_lg = QWidget()
        lay_lg = QVBoxLayout(page_lg)
        form_lg = QFormLayout()
        lay_lg.addLayout(form_lg)
        lg_path = QLineEdit(str(lg.get('model_path', '') or ''))
        lg_path.setPlaceholderText('Path to .gguf file (e.g. C:\\models\\gemma-2-2b-it-Q4_K_M.gguf)')
        lg_path.setMinimumWidth(520)
        lg_path.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lg_path.setClearButtonEnabled(True)
        lg_path.setToolTip(lg_path.text() or 'Select a .gguf model file')
        lg_path.textChanged.connect(lambda s: lg_path.setToolTip(s or 'Select a .gguf model file'))
        lg_browse = QPushButton('Browse…')

        def _pick_gguf() -> None:
            start = lg_path.text().strip()
            if start and os.path.isfile(start):
                start_dir = os.path.dirname(start)
            else:
                start_dir = ''
            picked, _ = QFileDialog.getOpenFileName(
                dialog, 'Select GGUF model', start_dir, 'GGUF models (*.gguf);;All files (*)'
            )
            if picked:
                lg_path.setText(picked)
                lg_path.setCursorPosition(len(picked))
                lg_path.end(False)

        lg_browse.clicked.connect(_pick_gguf)
        path_row = QHBoxLayout()
        path_row.addWidget(lg_path, 1)
        path_row.addWidget(lg_browse, 0)
        path_holder = QWidget()
        path_holder.setLayout(path_row)
        form_lg.addRow('Model file', path_holder)

        lg_chat_format = QComboBox()
        lg_chat_format.addItems(['auto', 'gemma', 'llama-3', 'llama-2', 'mistral-instruct', 'phi-3', 'qwen', 'chatml'])
        cf_cur = str(lg.get('chat_format', 'auto') or 'auto').lower() or 'auto'
        cf_idx = lg_chat_format.findText(cf_cur)
        lg_chat_format.setCurrentIndex(cf_idx if cf_idx >= 0 else 0)
        lg_chat_format.setToolTip(
            'Prompt template. "auto" picks one based on the filename '
            '(gemma → gemma, llama-3 → llama-3, etc.).'
        )

        lg_n_ctx = QSpinBox()
        lg_n_ctx.setRange(256, 131072)
        lg_n_ctx.setSingleStep(256)
        try:
            lg_n_ctx.setValue(int(lg.get('n_ctx', 4096) or 4096))
        except (TypeError, ValueError):
            lg_n_ctx.setValue(4096)

        lg_n_gpu = QSpinBox()
        lg_n_gpu.setRange(-1, 200)
        lg_n_gpu.setToolTip('GPU layers to offload (0 = CPU only, -1 = all).')
        try:
            lg_n_gpu.setValue(int(lg.get('n_gpu_layers', 0) or 0))
        except (TypeError, ValueError):
            lg_n_gpu.setValue(0)

        lg_n_threads = QSpinBox()
        lg_n_threads.setRange(0, 128)
        lg_n_threads.setToolTip('CPU threads (0 = auto: half of os.cpu_count()).')
        try:
            lg_n_threads.setValue(int(lg.get('n_threads', 0) or 0))
        except (TypeError, ValueError):
            lg_n_threads.setValue(0)

        lg_max_tokens = QSpinBox()
        lg_max_tokens.setRange(16, 32768)
        lg_max_tokens.setSingleStep(64)
        try:
            lg_max_tokens.setValue(int(lg.get('max_tokens', 1024) or 1024))
        except (TypeError, ValueError):
            lg_max_tokens.setValue(1024)

        form_lg.addRow('Chat format', lg_chat_format)
        form_lg.addRow('n_ctx', lg_n_ctx)
        form_lg.addRow('n_gpu_layers', lg_n_gpu)
        form_lg.addRow('n_threads', lg_n_threads)
        form_lg.addRow('max_tokens', lg_max_tokens)

        hint_lg = QLabel(
            'Runs a local .gguf model via llama-cpp-python. Install with '
            '"pip install llama-cpp-python" (CPU) or a CUDA/Metal wheel for GPU. '
            'Recommended for Gemma: download a Q4_K_M / Q5_K_M GGUF from Hugging Face.'
        )
        hint_lg.setWordWrap(True)
        lay_lg.addWidget(hint_lg)
        stack.addWidget(page_lg)

        def _sync_stack(*_args) -> None:
            stack.setCurrentIndex(provider_combo.currentIndex())

        provider_combo.currentIndexChanged.connect(_sync_stack)
        _sync_stack()

        _timeout_hint = QLabel(
            'Cloud APIs: Request timeout is per chat request (5–600 s). '
            'Local GGUF: same field caps total wait for load + ping (minimum 90 s); '
            'first load often needs 30–120 s — use 180–300 s if tests time out.'
        )
        _timeout_hint.setWordWrap(True)
        layout.addWidget(_timeout_hint)

        llm_test_status = QLabel('')
        llm_test_status.setWordWrap(True)
        layout.addWidget(llm_test_status)

        buttons = QHBoxLayout()
        test_btn = QPushButton('Test connection')
        test_btn.setToolTip(
            'Runs a minimal chat request using the values above (no need to Save first).'
        )
        save_btn = QPushButton('Save')
        close_btn = QPushButton('Close')
        buttons.addWidget(test_btn)
        buttons.addWidget(save_btn)
        buttons.addWidget(close_btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        class _LlTestBridge(QObject):
            finished = pyqtSignal(bool, str)

        _test_bridge = _LlTestBridge(dialog)

        def _on_test_finished(ok: bool, msg: str) -> None:
            test_btn.setEnabled(True)
            test_btn.setText('Test connection')
            llm_test_status.clear()
            if ok:
                QMessageBox.information(dialog, 'LLM test', msg)
                return
            needs_restart = (
                'access violation' in msg.lower()
                or 'restart the chat application' in msg.lower()
                or 'load is disabled in this process' in msg.lower()
            )
            box = QMessageBox(dialog)
            box.setIcon(QMessageBox.Critical if needs_restart else QMessageBox.Warning)
            box.setWindowTitle('LLM test failed')
            if needs_restart:
                box.setText(
                    'Restart the chat application before retrying.\n\n'
                    'A native llama.cpp crash leaves the Python process in an '
                    'unrecoverable state — no in-process fix exists.'
                )
                box.setInformativeText('Close this window, exit the application, '
                                       'then launch gui_chat.py again.')
                box.setDetailedText(msg)
            else:
                box.setText('LLM test failed')
                box.setInformativeText(msg)
            box.exec_()

        _test_bridge.finished.connect(_on_test_finished, Qt.QueuedConnection)

        def _current_provider_value() -> str:
            return _provider_values[provider_combo.currentIndex()]

        def _local_gguf_dict() -> dict:
            return {
                'model_path': lg_path.text().strip(),
                'chat_format': lg_chat_format.currentText().strip().lower() or 'auto',
                'n_ctx': int(lg_n_ctx.value()),
                'n_gpu_layers': int(lg_n_gpu.value()),
                'n_threads': int(lg_n_threads.value()),
                'max_tokens': int(lg_max_tokens.value()),
                'verbose': bool(lg.get('verbose', False)),
            }

        def do_test_connection() -> None:
            test_btn.setEnabled(False)
            test_btn.setText('Testing…')
            prov = _current_provider_value()
            if prov == PROVIDER_LOCAL_GGUF:
                llm_test_status.setText(
                    'Local GGUF: loading model can take 30–120 s on first use — please wait…'
                )
            else:
                llm_test_status.setText('Testing…')

            def _watchdog() -> None:
                if test_btn.text() == 'Testing…':
                    test_btn.setEnabled(True)
                    test_btn.setText('Test connection')
                    llm_test_status.clear()
                    QMessageBox.warning(
                        dialog,
                        'LLM test failed',
                        'The connection test did not finish within 5 minutes.\n\n'
                        'For Local GGUF: verify the .gguf path, try a smaller model, '
                        'or increase Request timeout (try 180–300 s).',
                    )

            QTimer.singleShot(300_000, _watchdog)

            local_gguf_dict = _local_gguf_dict()

            def _bg() -> None:
                try:
                    msg = llm_connection_test(
                        prov,
                        float(timeout_s.value()),
                        {
                            'endpoint': az_endpoint.text().strip(),
                            'deployment': az_deployment.text().strip(),
                            'api_version': az_api_version.text().strip() or '2024-02-15-preview',
                            'api_key': az_api_key.text().strip(),
                        },
                        {
                            'api_key': oa_key.text().strip(),
                            'model': oa_model.text().strip() or 'gpt-4o-mini',
                            'base_url': oa_base.text().strip(),
                        },
                        local_gguf_dict,
                    )
                    _test_bridge.finished.emit(True, msg)
                except BaseException as e:
                    err = str(e).strip() or type(e).__name__
                    _test_bridge.finished.emit(False, err)

            threading.Thread(target=_bg, daemon=True).start()

        test_btn.clicked.connect(do_test_connection)

        def do_save_and_close() -> None:
            try:
                prov = _current_provider_value()
                tsec = int(timeout_s.value())
                config['llm'] = {
                    'provider': prov,
                    'timeout_seconds': tsec,
                    'auto_analyze_results': bool(auto_analyze_cb.isChecked()),
                    'chat_mode': (
                        CHAT_MODE_PLAN if chat_mode_combo.currentIndex() == 1 else CHAT_MODE_AGENT
                    ),
                    'automation_loop': {
                        'enabled': bool(auto_loop_cb.isChecked()),
                        'max_iterations': int(max_iter_spin.value()),
                        'auto_repair_on_fail': bool(auto_repair_cb.isChecked()),
                        'closed_loop_agent': bool(closed_loop_cb.isChecked()),
                        'multi_turn_history': int(history_spin.value()),
                    },
                }
                config['azure_openai'] = {
                    'endpoint': az_endpoint.text().strip(),
                    'deployment': az_deployment.text().strip(),
                    'api_version': az_api_version.text().strip() or '2024-02-15-preview',
                    'api_key': az_api_key.text().strip(),
                }
                config['openai_api'] = {
                    'api_key': oa_key.text().strip(),
                    'model': oa_model.text().strip() or 'gpt-4o-mini',
                    'base_url': oa_base.text().strip(),
                }
                config['local_gguf'] = _local_gguf_dict()
                cfg_mgr.config = config
                cfg_mgr.save_config()
                cfg_mgr.load_config()
                self._apply_chat_mode_from_config()
                self._sync_chat_mode_combo()
                self._append_text('LLM settings saved.\n\n')
                dialog.accept()
            except Exception as exc:
                QMessageBox.critical(dialog, 'Save failed', str(exc))

        save_btn.clicked.connect(do_save_and_close)
        close_btn.clicked.connect(dialog.reject)

        dialog.exec_()

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
    app = QApplication(sys.argv)
    fusion = QStyleFactory.create('Fusion')
    if fusion is not None:
        app.setStyle(fusion)
    app.setApplicationName('LabAutomationChat')
    app.setApplicationDisplayName('Lab Automation Chat')
    icon_path = gui_app_icon_path_preferred(_REPO_FILE)
    if icon_path:
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)
    else:
        app_icon = None
    window = ChatWindow()
    if app_icon is not None:
        window.setWindowIcon(app_icon)
    window.show()
    sys.exit(app.exec_())
