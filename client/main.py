import sys
import os

# Fix high-DPI on Windows
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from login_window import LoginWindow
from messenger_window import MessengerWindow
from api_client import APIClient


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CompanyChat")
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    api = APIClient()
    login_win = LoginWindow()

    def on_login_success(user_data: dict, server_url: str):
        api.setup(server_url, user_data["token"])
        messenger = MessengerWindow(user_data["user"], server_url, api)
        messenger.show()
        login_win.close()

    login_win.login_success.connect(on_login_success)
    login_win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
