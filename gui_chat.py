import re
import sys
import os
import json
from datetime import datetime

# Add src directory to path BEFORE importing testbench modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from testbench.chat_plotting import try_extract_plot_command, render_plot_to_png_bytes
from testbench.command_parser import CommandParser, handle_help
from testbench.command_registry import CommandRegistry
from testbench._paths import default_config_file, repo_root

_CONFIG_DIALOG_START = str(repo_root() / 'config')


def try_parse_quoted_heading(command: str):
    """Heading only when the whole line is wrapped in double quotes, e.g. ``\"Power Cycle Test\"``."""
    s = (command or "").strip()
    m = re.match(r'^"(.*)"\s*$', s, re.DOTALL)
    if not m:
        return None
    inner = (m.group(1) or "").strip()
    return inner if inner else None


class CommandCompleter:
    """Helper class to generate autocomplete suggestions."""

    def __init__(self, registry):
        self.registry = registry
        self.all_commands = self._build_command_list()

    def _build_command_list(self):
        """Build list of all available commands in 'bench.<category>.<action>' or 'bc.<category>.<action>' format."""
        tops = ['bench', 'bc']
        commands = []
        for category, actions in self.registry.get_all_commands().items():
            for action in actions.keys():
                for top in tops:
                    commands.append(f"{top}.{category}.{action}")
        return sorted(set(commands))

    def get_suggestions(self, partial_input: str, max_suggestions: int = 10) -> list:
        """Get autocomplete suggestions for the given partial input."""
        text = partial_input.strip()
        if not text:
            return self.all_commands[:max_suggestions]

        last_fragment = re.split(r'[;\n\r]+', text)[-1].strip().lower()
        if not last_fragment:
            return self.all_commands[:max_suggestions]

        suggestions = [
            cmd for cmd in self.all_commands
            if cmd.lower().startswith(last_fragment)
        ]
        return suggestions[:max_suggestions]


def run_chat_command(
    command: str,
    registry,
    parser,
    append_text,
    append_error,
    append_heading,
    append_plot_from_data,
) -> None:
    """Run a single user command: help, quoted heading, plot(...), or bench/bc."""
    cmd = (command or "").strip()
    if not cmd:
        return
    if cmd.lower() == "help":
        response = handle_help([], registry)
        append_text(f"\n{response}\n\n")
        return
    if cmd.lower().startswith("help "):
        args = cmd[5:].strip().split()
        response = handle_help(args, registry)
        append_text(f"\n{response}\n\n")
        return

    title = try_parse_quoted_heading(cmd)
    if title is not None:
        append_heading(title)
        return

    plot_inner = try_extract_plot_command(cmd)
    if plot_inner is not None:
        parsed = parser.parse(plot_inner)
        if not parsed:
            append_error(
                "Error: plot(inner) needs a valid bench command, e.g. plot(bc.sg.measure frequency)\n\n"
            )
            return
        try:
            result = registry.execute(parsed["category"], parsed["action"], parsed["args"])
            append_text(f"Result: {result}\n")
            append_plot_from_data(result)
            append_text("\n")
        except ValueError as e:
            append_error(f"Error: {e}\n\n")
        except Exception as e:
            append_error(f"Error: {e}\n\n")
        return

    parsed = parser.parse(cmd)
    if not parsed:
        append_error(
            "Error: Invalid command format. Expected: bench.<category>.<action> or bc.<category>.<action> [args...]\n"
        )
        append_error("       Example: bench.ps.on True or bc.ps.on True\n")
        append_error("       Type 'help' for all available commands\n\n")
        return

    try:
        result = registry.execute(parsed["category"], parsed["action"], parsed["args"])
        response = "OK" if result is None else str(result)
        append_text(f"Result: {response}\n\n")
    except ValueError as e:
        append_error(f"Error: {e}\n\n")
    except Exception as e:
        append_error(f"Error: {e}\n\n")


try:
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
    )
    from PyQt5.QtCore import Qt, QEvent, QTimer
    from PyQt5.QtGui import QFont, QGuiApplication, QImage, QPalette, QTextCursor, QTextCharFormat
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False


if PYQT_AVAILABLE:
    class ChatWindow(QMainWindow):
        def __init__(self):
            super().__init__()
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

            settings_menu = self.menuBar().addMenu('Settings')
            settings_action = settings_menu.addAction('Bench Settings')
            settings_action.triggered.connect(self.open_bench_settings)

            help_menu = self.menuBar().addMenu('Help')
            show_help_action = help_menu.addAction('Show Commands')
            show_help_action.triggered.connect(self.show_help)

            central_widget = QWidget()
            self.layout = QVBoxLayout(central_widget)

            self.chat_display = QTextEdit()
            self.chat_display.setReadOnly(True)
            self.layout.addWidget(self.chat_display)

            # Chat-style composer row (input + small send button)
            composer_row = QHBoxLayout()

            self.input_line = QTextEdit()
            self.input_line.setAcceptRichText(False)
            # Make command input smaller; let chat take most space
            self.input_line.setFixedHeight(90)
            self.input_line.installEventFilter(self)
            self.input_line.textChanged.connect(self.on_input_changed)
            self.input_line.setPlaceholderText('Enter commands here. Use ; or newline to separate multiple commands.')
            composer_row.addWidget(self.input_line, 1)

            action_col = QVBoxLayout()

            self.clear_button = QPushButton('✕')
            self.clear_button.setToolTip('Clear screen')
            self.clear_button.setFixedSize(44, 32)
            self.clear_button.setStyleSheet("""
                QPushButton {
                    border: 1px solid #cfcfcf;
                    border-radius: 10px;
                    background: white;
                    font-size: 14px;
                    padding: 0px;
                }
                QPushButton:hover { background: #f5f5f5; }
                QPushButton:pressed { background: #eeeeee; }
            """)
            self.clear_button.clicked.connect(self.clear_screen)
            action_col.addWidget(self.clear_button, 0, Qt.AlignRight)

            self.send_button = QPushButton('▶')
            self.send_button.setToolTip('Send')
            self.send_button.setFixedSize(44, 44)
            self.send_button.setStyleSheet("""
                QPushButton {
                    border: 1px solid #cfcfcf;
                    border-radius: 10px;
                    background: white;
                    font-size: 18px;
                    padding: 0px;
                }
                QPushButton:hover { background: #f5f5f5; }
                QPushButton:pressed { background: #eeeeee; }
            """)
            self.send_button.clicked.connect(self._on_send_or_stop_clicked)
            action_col.addWidget(self.send_button, 0, Qt.AlignRight)

            composer_row.addLayout(action_col)

            self.layout.addLayout(composer_row)

            self.suggestions_list = QListWidget()
            self.suggestions_list.setMaximumHeight(140)
            self.suggestions_list.itemClicked.connect(self.on_suggestion_clicked)
            self.layout.addWidget(self.suggestions_list)
            self.suggestions_list.hide()

            self.setCentralWidget(central_widget)

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
            self._delay_timer = QTimer(self)
            self._delay_timer.setSingleShot(True)
            self._delay_timer.timeout.connect(self._on_delay_timer_done)

            self.status_bar = self.statusBar()
            self.update_status_bar()

            self._append_text('Lab Automation Chat\n')
            self._append_text("Type 'help' for available commands\n")
            self._append_text("Type 'bench.' or 'bc.' to see command suggestions\n")
            self._append_text("Use semicolons or Shift+Enter for multiple commands.\n")
            self._append_text("Use bench.config.* to manage real/sim mode and discovery.\n")
            self._append_text("Use bench.<inst>.raw <SCPI> for raw instrument commands in real mode.\n")
            self._append_text(
                "Plot: plot(bc.sg.measure frequency) — scalar; plot list data — 1D; "
                "plot(bc.osc.get_trace 1) after bc.osc.run — time vs voltage.\n"
            )
            self._append_text("History: Up/Down recalls last commands (when suggestions are hidden).\n")
            self._append_text('Section heading: wrap the title in double quotes, e.g. "Power Cycle Test".\n')
            self._append_text('Delay: use delay 10 to wait 10 seconds before the next command; Send becomes Stop.\n')
            self._append_text('=' * 60 + '\n\n')

        def _set_run_button_sequence_mode(self, running: bool) -> None:
            if running:
                self.send_button.setText('Stop')
                self.send_button.setToolTip('Stop sequence')
            else:
                self.send_button.setText('▶')
                self.send_button.setToolTip('Send')

        def _on_send_or_stop_clicked(self) -> None:
            if self._sequence_active:
                self._delay_timer.stop()
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

        def _on_delay_timer_done(self) -> None:
            if self._sequence_active:
                self._run_next_sequence_step()

        def _start_command_sequence(self, commands: list) -> None:
            self._sequence_active = True
            self._sequence_queue = list(commands)
            self._sequence_index = 0
            self._set_run_button_sequence_mode(True)
            self._run_next_sequence_step()

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

        def send_command(self):
            if self._sequence_active:
                return
            raw_text = self.input_line.toPlainText().strip()
            if not raw_text:
                return

            self.suggestions_list.hide()
            self._history_append(raw_text)
            self._history_browse_index = None
            commands = [cmd.strip() for cmd in re.split(r'[;\n\r]+', raw_text) if cmd.strip()]
            self.input_line.clear()
            self.update_status_bar()
            if not commands:
                return
            self._start_command_sequence(commands)

        def _default_char_format(self) -> QTextCharFormat:
            fmt = QTextCharFormat()
            fmt.setForeground(self.chat_display.palette().color(QPalette.Active, QPalette.Text))
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
            hf.setForeground(self.chat_display.palette().color(QPalette.Active, QPalette.Text))
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
            char_format.setForeground(Qt.red)
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
            self.status_bar.showMessage(f"Mode: {mode} | Instruments: {instruments}")

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
                _CONFIG_DIALOG_START,
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

        def show_help(self):
            response = handle_help([], self.registry)
            self._append_text(f'\n{response}\n\n')

    def main():
        app = QApplication(sys.argv)
        window = ChatWindow()
        window.show()
        sys.exit(app.exec_())
else:
    try:
        import tkinter as tk
        import tkinter.font as tkfont
        from tkinter.scrolledtext import ScrolledText
        from tkinter import filedialog
        from tkinter import messagebox

        class ChatWindow:
            def __init__(self):
                self.root = tk.Tk()
                self.root.title('Lab Automation Chat')
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

                self.menu = tk.Menu(self.root)
                self.root.config(menu=self.menu)

                file_menu = tk.Menu(self.menu)
                self.menu.add_cascade(label='File', menu=file_menu)
                file_menu.add_command(label='Save Log', command=self.save_log)
                file_menu.add_command(label='Load Config', command=self.load_config)
                file_menu.add_command(label='Exit', command=self.root.quit)

                scripts_menu = tk.Menu(self.menu)
                self.menu.add_cascade(label='Scripts', menu=scripts_menu)
                scripts_menu.add_command(label='Load Script', command=self.load_script)

                settings_menu = tk.Menu(self.menu)
                self.menu.add_cascade(label='Settings', menu=settings_menu)
                settings_menu.add_command(label='Bench Settings', command=self.open_bench_settings)

                help_menu = tk.Menu(self.menu)
                self.menu.add_cascade(label='Help', menu=help_menu)
                help_menu.add_command(label='Show Commands', command=self.show_help)

                self.chat_display = ScrolledText(self.root, state='disabled', wrap='word')
                self.chat_display.pack(fill='both', expand=True, padx=8, pady=8)
                self.chat_display.tag_configure("error", foreground="red")
                _base_tf = tkfont.nametofont("TkTextFont")
                _act = _base_tf.actual()
                self._heading_font = tkfont.Font(
                    self.root,
                    family=_act["family"],
                    size=_act["size"] + 2,
                    weight="bold",
                    underline=True,
                )
                self.chat_display.tag_configure("heading", font=self._heading_font)

                self.input_frame = tk.Frame(self.root)
                self.input_frame.pack(fill='x', padx=8, pady=(0, 0))

                # Smaller command box; chat gets most space
                self.input_line = tk.Text(self.input_frame, height=3, wrap='word')
                self.input_line.pack(side='left', fill='x', expand=True, padx=(0, 8))
                self.input_line.bind('<Return>', self.on_text_return)
                self.input_line.bind('<KeyRelease>', self.on_input_changed)
                self.input_line.bind('<Up>', self.on_suggestion_up)
                self.input_line.bind('<Down>', self.on_suggestion_down)
                self.input_line.bind('<Tab>', self.on_suggestion_tab)

                # Small chat-style send button
                self.action_frame = tk.Frame(self.input_frame)
                self.action_frame.pack(side='right')

                self.clear_button = tk.Button(self.action_frame, text='✕', command=self.clear_screen, width=3, height=1)
                self.clear_button.pack(side='top', pady=(0, 6))

                self.send_button = tk.Button(
                    self.action_frame, text='▶', command=self._on_send_or_stop_clicked, width=4, height=2
                )
                self.send_button.pack(side='top')

                self.suggestions_frame = tk.Frame(self.root)
                self.suggestions_frame.pack(fill='x', padx=8, pady=(0, 8))

                self.suggestions_list = tk.Listbox(self.suggestions_frame, height=5)
                self.suggestions_list.pack(fill='x')
                self.suggestions_list.bind('<Button-1>', self.on_suggestion_clicked)
                self.suggestions_list.bind('<Return>', self.on_suggestion_select)
                self.suggestions_list.pack_forget()

                self.status_label = tk.Label(self.root, text="", anchor='w')
                self.status_label.pack(fill='x', padx=8, pady=(0, 8))

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
                self._delay_after_id = None
                self._pending_step_after_id = None

                self._append_text('Lab Automation Chat\n')
                self._append_text("Type 'help' for available commands\n")
                self._append_text("Type 'bench.' or 'bc.' to see command suggestions\n")
                self._append_text("Use semicolons or Shift+Enter for multiple commands.\n")
                self._append_text("Use bench.config.* to manage real/sim mode and discovery.\n")
                self._append_text("Use bench.<inst>.raw <SCPI> for raw instrument commands in real mode.\n")
                self._append_text(
                    "Plot: plot(bc.sg.measure frequency) — scalar; 1D list plots vs index; "
                    "plot(bc.osc.get_trace 1) after bc.osc.run — time vs voltage.\n"
                )
                self._append_text("History: Up/Down recalls last commands (when suggestions are hidden).\n")
                self._append_text('Section heading: wrap the title in double quotes, e.g. "Power Cycle Test".\n')
                self._append_text('Delay: use delay 10 to wait 10 seconds before the next command; Send becomes Stop.\n')
                self._append_text('=' * 60 + '\n\n')

                self.update_status_label()

            def _set_run_button_sequence_mode(self, running: bool) -> None:
                if running:
                    self.send_button.config(text='Stop')
                else:
                    self.send_button.config(text='▶')

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

            def _schedule_next_sequence_step(self, delay_ms: int = 0) -> None:
                self._cancel_after_id('_pending_step_after_id')
                self._pending_step_after_id = self.root.after(delay_ms, self._run_next_sequence_step)

            def _on_delay_elapsed(self) -> None:
                self._delay_after_id = None
                if self._sequence_active:
                    self._run_next_sequence_step()

            def _start_command_sequence(self, commands: list) -> None:
                self._sequence_active = True
                self._sequence_queue = list(commands)
                self._sequence_index = 0
                self._set_run_button_sequence_mode(True)
                self._run_next_sequence_step()

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

                self.suggestions_list.pack_forget()
                self._history_append(raw_text)
                self._history_browse_index = None
                commands = [cmd.strip() for cmd in re.split(r'[;\n\r]+', raw_text) if cmd.strip()]
                self.input_line.delete('1.0', tk.END)
                self.update_status_label()
                if not commands:
                    return
                self._start_command_sequence(commands)

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
                self.status_label.config(text=f"Mode: {mode} | Instruments: {instruments}")

            def save_log(self):
                text = self.chat_display.get('1.0', tk.END)
                filename = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text Files', '*.txt'), ('All Files', '*')])
                if filename:
                    with open(filename, 'w') as f:
                        f.write(text)

            def load_config(self):
                filename = filedialog.askopenfilename(
                    title='Load Config',
                    initialdir=_CONFIG_DIALOG_START,
                    filetypes=[('JSON Files', '*.json'), ('All Files', '*.*')]
                )
                if not filename:
                    return

                try:
                    self.registry.config_manager.load_config(filename)
                    self.registry.reload_instruments()
                    self.completer = CommandCompleter(self.registry)
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
                        self.update_status_label()
                        self.on_input_changed()
                        self._append_text('Bench settings saved and reloaded.\n\n')
                        top.destroy()
                    except Exception as exc:
                        messagebox.showerror('Save failed', str(exc), parent=top)

                tk.Button(btn_frame, text='Save', command=do_save_and_close).pack(side='left')
                tk.Button(btn_frame, text='Cancel', command=top.destroy).pack(side='left', padx=(8, 0))

            def show_help(self):
                response = handle_help([], self.registry)
                self._append_text(f'\n{response}\n\n')

        def main():
            window = ChatWindow()
            window.root.mainloop()
    except ImportError:
        def main():
            print('Error: GUI dependencies are not installed.')
            print('Install either PyQt5 or use a Python environment with tkinter available.')
            sys.exit(1)


if __name__ == '__main__':
    main()
