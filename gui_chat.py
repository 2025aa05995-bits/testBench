import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QTextEdit, QLineEdit, QPushButton

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
            # Placeholder for command processing
            self.chat_display.append(f"System: [Processing '{command}']")
            self.input_line.clear()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ChatWindow()
    window.show()
    sys.exit(app.exec_())
