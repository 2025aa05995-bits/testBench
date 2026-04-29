import re
import sys
import os

# Add src directory to path BEFORE importing testbench modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from command_parser import CommandParser, handle_help
from testbench.command_registry import CommandRegistry


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


try:
    from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QTextEdit, QPushButton, QListWidget
    from PyQt5.QtCore import Qt, QEvent
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False


if PYQT_AVAILABLE:
    class ChatWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle('Lab Automation Chat')
            self.setGeometry(100, 100, 800, 600)
            self.layout = QVBoxLayout()

            self.chat_display = QTextEdit()
            self.chat_display.setReadOnly(True)
            self.layout.addWidget(self.chat_display)

            self.input_line = QTextEdit()
            self.input_line.setAcceptRichText(False)
            self.input_line.installEventFilter(self)
            self.input_line.textChanged.connect(self.on_input_changed)
            self.input_line.setPlaceholderText('Enter commands here. Use ; or newline to separate multiple commands.')
            self.layout.addWidget(self.input_line)

            self.suggestions_list = QListWidget()
            self.suggestions_list.itemClicked.connect(self.on_suggestion_clicked)
            self.layout.addWidget(self.suggestions_list)
            self.suggestions_list.hide()

            self.send_button = QPushButton('Send')
            self.send_button.clicked.connect(self.send_command)
            self.layout.addWidget(self.send_button)

            self.setLayout(self.layout)

            self.parser = CommandParser()
            self.registry = CommandRegistry()
            self.completer = CommandCompleter(self.registry)

            self._append_text('Lab Automation Chat\n')
            self._append_text("Type 'help' for available commands\n")
            self._append_text("Type 'bench.' or 'bc.' to see command suggestions\n")
            self._append_text("Use semicolons or Shift+Enter for multiple commands.\n")
            self._append_text('=' * 60 + '\n\n')

        def eventFilter(self, obj, event):
            if obj is self.input_line and event.type() == QEvent.KeyPress:
                if event.key() in {Qt.Key_Return, Qt.Key_Enter}:
                    if event.modifiers() & Qt.ShiftModifier:
                        return False
                    self.send_command()
                    return True
            return super().eventFilter(obj, event)

        def on_input_changed(self):
            text = self.input_line.toPlainText().strip()
            if text.startswith(('bench.', 'bc.')):
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
            else:
                self.suggestions_list.hide()

        def on_suggestion_clicked(self, item):
            self.input_line.setPlainText(item.text())
            self.suggestions_list.hide()

        def send_command(self):
            raw_text = self.input_line.toPlainText().strip()
            if not raw_text:
                return

            self.suggestions_list.hide()
            commands = [cmd.strip() for cmd in re.split(r'[;\n\r]+', raw_text) if cmd.strip()]
            for command in commands:
                self._append_text(f'You: {command}\n')
                if command.lower() == 'help':
                    response = handle_help([], self.registry)
                    self._append_text(f'\n{response}\n\n')
                    continue
                elif command.lower().startswith('help '):
                    args = command[5:].strip().split()
                    response = handle_help(args, self.registry)
                    self._append_text(f'\n{response}\n\n')
                    continue

                parsed = self.parser.parse(command)
                if not parsed:
                    self._append_text(
                        'Error: Invalid command format. Expected: bench.<category>.<action> or bc.<category>.<action> [args...]\n')
                    self._append_text('       Example: bench.ps.on True or bc.ps.on True\n')
                    self._append_text('       Type \'help\' for all available commands\n\n')
                    continue

                try:
                    result = self.registry.execute(parsed['category'], parsed['action'], parsed['args'])
                    response = 'OK' if result is None else str(result)
                    self._append_text(f'Result: {response}\n\n')
                except ValueError as e:
                    self._append_text(f'Error: {e}\n\n')
                except Exception as e:
                    self._append_text(f'Error: {e}\n\n')

            self.input_line.clear()

        def _append_text(self, text: str):
            self.chat_display.append(text)

    def main():
        app = QApplication(sys.argv)
        window = ChatWindow()
        window.show()
        sys.exit(app.exec_())
else:
    try:
        import tkinter as tk
        from tkinter.scrolledtext import ScrolledText

        class ChatWindow:
            def __init__(self):
                self.root = tk.Tk()
                self.root.title('Lab Automation Chat')
                self.root.geometry('800x650')

                self.chat_display = ScrolledText(self.root, state='disabled', wrap='word')
                self.chat_display.pack(fill='both', expand=True, padx=8, pady=8)

                self.input_frame = tk.Frame(self.root)
                self.input_frame.pack(fill='x', padx=8, pady=(0, 0))

                self.input_line = tk.Text(self.input_frame, height=4, wrap='word')
                self.input_line.pack(side='left', fill='x', expand=True)
                self.input_line.bind('<Return>', self.on_text_return)
                self.input_line.bind('<KeyRelease>', self.on_input_changed)
                self.input_line.bind('<Up>', self.on_suggestion_up)
                self.input_line.bind('<Down>', self.on_suggestion_down)

                self.send_button = tk.Button(self.input_frame, text='Send', command=self.send_command)
                self.send_button.pack(side='right', padx=(8, 0))

                self.suggestions_frame = tk.Frame(self.root)
                self.suggestions_frame.pack(fill='x', padx=8, pady=(0, 8))

                self.suggestions_list = tk.Listbox(self.suggestions_frame, height=5)
                self.suggestions_list.pack(fill='x')
                self.suggestions_list.bind('<Button-1>', self.on_suggestion_clicked)
                self.suggestions_list.bind('<Return>', self.on_suggestion_select)
                self.suggestions_list.pack_forget()

                self.parser = CommandParser()
                self.registry = CommandRegistry()
                self.completer = CommandCompleter(self.registry)
                self.selected_suggestion_index = -1

                self._append_text('Lab Automation Chat\n')
                self._append_text("Type 'help' for available commands\n")
                self._append_text("Type 'bench.' or 'bc.' to see command suggestions\n")
                self._append_text("Use semicolons or Shift+Enter for multiple commands.\n")
                self._append_text('=' * 60 + '\n\n')

            def on_input_changed(self, event=None):
                text = self.input_line.get('1.0', tk.END).strip()
                if text.startswith(('bench.', 'bc.')):
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

            def on_suggestion_clicked(self, event):
                selection = self.suggestions_list.curselection()
                if selection:
                    suggestion = self.suggestions_list.get(selection[0])
                    self.input_line.delete('1.0', tk.END)
                    self.input_line.insert('1.0', suggestion)
                    self.suggestions_list.pack_forget()

            def on_suggestion_select(self, event):
                selection = self.suggestions_list.curselection()
                if selection:
                    suggestion = self.suggestions_list.get(selection[0])
                    self.input_line.delete('1.0', tk.END)
                    self.input_line.insert('1.0', suggestion)
                    self.suggestions_list.pack_forget()
                return 'break'

            def on_text_return(self, event=None):
                if event.state & 0x0001:
                    self.input_line.insert('insert', '\n')
                    return 'break'
                self.send_command()
                return 'break'

            def send_command(self):
                raw_text = self.input_line.get('1.0', tk.END).strip()
                if not raw_text:
                    return

                self.suggestions_list.pack_forget()
                commands = [cmd.strip() for cmd in re.split(r'[;\n\r]+', raw_text) if cmd.strip()]
                for command in commands:
                    self._append_text(f'You: {command}\n')
                    if command.lower() == 'help':
                        response = handle_help([], self.registry)
                        self._append_text(f'\n{response}\n\n')
                        continue
                    elif command.lower().startswith('help '):
                        args = command[5:].strip().split()
                        response = handle_help(args, self.registry)
                        self._append_text(f'\n{response}\n\n')
                        continue

                    parsed = self.parser.parse(command)
                    if not parsed:
                        self._append_text(
                            'Error: Invalid command format. Expected: bench.<category>.<action> or bc.<category>.<action> [args...]\n')
                        self._append_text('       Example: bench.ps.on True or bc.ps.on True\n')
                        self._append_text('       Type \'help\' for all available commands\n\n')
                        continue

                    try:
                        result = self.registry.execute(parsed['category'], parsed['action'], parsed['args'])
                        response = 'OK' if result is None else str(result)
                        self._append_text(f'Result: {response}\n\n')
                    except ValueError as e:
                        self._append_text(f'Error: {e}\n\n')
                    except Exception as e:
                        self._append_text(f'Error: {e}\n\n')

                self.input_line.delete('1.0', tk.END)

            def _append_text(self, text: str):
                self.chat_display.configure(state='normal')
                self.chat_display.insert('end', text)
                self.chat_display.configure(state='disabled')
                self.chat_display.see('end')

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
