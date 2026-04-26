import sys

try:
    from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QTextEdit, QLineEdit, QPushButton
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

if PYQT_AVAILABLE:
    class ChatWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle('Lab Automation Chat')
            self.setGeometry(100, 100, 500, 400)
            self.layout = QVBoxLayout()

            self.chat_display = QTextEdit()
            self.chat_display.setReadOnly(True)
            self.layout.addWidget(self.chat_display)

            self.input_line = QLineEdit()
            self.input_line.returnPressed.connect(self.send_command)
            self.layout.addWidget(self.input_line)

            self.send_button = QPushButton('Send')
            self.send_button.clicked.connect(self.send_command)
            self.layout.addWidget(self.send_button)

            self.setLayout(self.layout)

        def send_command(self):
            command = self.input_line.text()
            if command:
                self.chat_display.append(f"You: {command}")
                self.chat_display.append(f"System: [Processing '{command}']")
                self.input_line.clear()

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
                self.root.geometry('500x400')

                self.chat_display = ScrolledText(
                    self.root, state='disabled', wrap='word')
                self.chat_display.pack(
                    fill='both', expand=True, padx=8, pady=8)

                self.input_frame = tk.Frame(self.root)
                self.input_frame.pack(fill='x', padx=8, pady=(0, 8))

                self.input_line = tk.Entry(self.input_frame)
                self.input_line.pack(side='left', fill='x', expand=True)
                self.input_line.bind(
                    '<Return>', lambda event: self.send_command())

                self.send_button = tk.Button(
                    self.input_frame, text='Send', command=self.send_command)
                self.send_button.pack(side='right', padx=(8, 0))

            def send_command(self):
                command = self.input_line.get().strip()
                if command:
                    self._append_text(f"You: {command}\n")
                    self._append_text(f"System: [Processing '{command}']\n")
                    self.input_line.delete(0, tk.END)

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
            print(
                'Install either PyQt5 or use a Python environment with tkinter available.')
            sys.exit(1)

if __name__ == '__main__':
    main()
