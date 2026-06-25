from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QSpacerItem, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QObject
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor, QPen, QBrush

import requests


class LoginWorker(QObject):
    success = pyqtSignal(dict, str)   # (user_data, server_url)
    failed  = pyqtSignal(str)

    def __init__(self, server_url: str, username: str, password: str):
        super().__init__()
        self.server_url = server_url.rstrip("/")
        self.username   = username
        self.password   = password

    def run(self):
        try:
            resp = requests.post(
                f"{self.server_url}/api/auth/login",
                json={"username": self.username, "password": self.password},
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json()
            self.success.emit(data, self.server_url)
        except requests.exceptions.ConnectionError:
            self.failed.emit("Không thể kết nối tới server. Kiểm tra địa chỉ server.")
        except requests.exceptions.Timeout:
            self.failed.emit("Server không phản hồi. Vui lòng thử lại.")
        except requests.exceptions.HTTPError as e:
            try:
                msg = e.response.json().get("detail", "Đăng nhập thất bại")
            except Exception:
                msg = "Đăng nhập thất bại"
            self.failed.emit(msg)
        except Exception as e:
            self.failed.emit(str(e))


class LoginWindow(QWidget):
    login_success = pyqtSignal(dict, str)   # user, server_url

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CompanyChat — Đăng nhập")
        self.setFixedSize(440, 560)
        self.setStyleSheet("""
            QWidget { background: #18191a; color: #e4e6ea; font-family: 'Segoe UI', Arial; }
            QLineEdit {
                background: #3a3b3c; border: 1.5px solid transparent;
                border-radius: 10px; padding: 11px 14px;
                color: #e4e6ea; font-size: 14px;
            }
            QLineEdit:focus { border-color: #0084ff; }
            QLineEdit::placeholder { color: #65686e; }
            QPushButton#login_btn {
                background: #0084ff; border: none; border-radius: 10px;
                color: white; font-size: 15px; font-weight: 600;
                padding: 12px; min-height: 44px;
            }
            QPushButton#login_btn:hover   { background: #0073e0; }
            QPushButton#login_btn:pressed { background: #0062bf; }
            QPushButton#login_btn:disabled { background: #3a3b3c; color: #65686e; }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(48, 0, 48, 0)
        outer.setSpacing(0)

        outer.addStretch(2)

        # Logo + Title
        logo_label = QLabel("💬")
        logo_label.setFixedSize(68, 68)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setStyleSheet("""
            background: #0084ff; border-radius: 18px;
            font-size: 34px;
        """)

        logo_row = QHBoxLayout()
        logo_row.addStretch()
        logo_row.addWidget(logo_label)
        logo_row.addStretch()
        outer.addLayout(logo_row)
        outer.addSpacing(18)

        title = QLabel("CompanyChat")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: 700; color: #e4e6ea;")
        outer.addWidget(title)

        subtitle = QLabel("Đăng nhập để bắt đầu")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 14px; color: #b0b3b8; margin-top: 4px;")
        outer.addWidget(subtitle)

        outer.addSpacing(32)

        # Error label
        self.err_label = QLabel("")
        self.err_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.err_label.setWordWrap(True)
        self.err_label.setStyleSheet("""
            background: rgba(255,59,48,.12); color: #ff6b6b;
            border: 1px solid rgba(255,59,48,.3); border-radius: 8px;
            padding: 8px 12px; font-size: 13px;
        """)
        self.err_label.hide()
        outer.addWidget(self.err_label)
        outer.addSpacing(4)

        # Server URL
        server_lbl = QLabel("Địa chỉ Server")
        server_lbl.setStyleSheet("font-size: 13px; color: #b0b3b8; font-weight: 500; margin-bottom: 5px;")
        outer.addWidget(server_lbl)

        self.server_input = QLineEdit()
        self.server_input.setPlaceholderText("http://192.168.1.100:8000")
        self.server_input.setText("http://localhost:8000")
        outer.addWidget(self.server_input)
        outer.addSpacing(14)

        # Username
        user_lbl = QLabel("Tên đăng nhập")
        user_lbl.setStyleSheet("font-size: 13px; color: #b0b3b8; font-weight: 500; margin-bottom: 5px;")
        outer.addWidget(user_lbl)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("username")
        outer.addWidget(self.username_input)
        outer.addSpacing(14)

        # Password
        pw_lbl = QLabel("Mật khẩu")
        pw_lbl.setStyleSheet("font-size: 13px; color: #b0b3b8; font-weight: 500; margin-bottom: 5px;")
        outer.addWidget(pw_lbl)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("••••••")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self._do_login)
        outer.addWidget(self.password_input)
        outer.addSpacing(22)

        # Login button
        self.login_btn = QPushButton("Đăng nhập")
        self.login_btn.setObjectName("login_btn")
        self.login_btn.clicked.connect(self._do_login)
        outer.addWidget(self.login_btn)

        outer.addStretch(3)

        self._worker = None
        self._thread = None

    def _do_login(self):
        server_url = self.server_input.text().strip()
        username   = self.username_input.text().strip()
        password   = self.password_input.text()

        if not server_url:
            self._show_error("Vui lòng nhập địa chỉ server")
            return
        if not username:
            self._show_error("Vui lòng nhập tên đăng nhập")
            return
        if not password:
            self._show_error("Vui lòng nhập mật khẩu")
            return

        self.err_label.hide()
        self.login_btn.setEnabled(False)
        self.login_btn.setText("Đang đăng nhập...")

        self._worker = LoginWorker(server_url, username, password)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.success.connect(self._on_success)
        self._worker.failed.connect(self._on_failed)
        self._worker.success.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def _on_success(self, data: dict, server_url: str):
        self.login_btn.setEnabled(True)
        self.login_btn.setText("Đăng nhập")
        self.login_success.emit(data, server_url)

    def _on_failed(self, msg: str):
        self.login_btn.setEnabled(True)
        self.login_btn.setText("Đăng nhập")
        self._show_error(msg)

    def _show_error(self, msg: str):
        self.err_label.setText(msg)
        self.err_label.show()
