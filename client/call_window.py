from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtCore import QUrl, Qt


class _VideoPage(QWebEnginePage):
    """Auto-grant camera/microphone permissions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.featurePermissionRequested.connect(self._grant)

    def _grant(self, url, feature):
        self.setFeaturePermission(
            url, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
        )


class CallWindow(QDialog):
    def __init__(self, call_url: str, peer_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Video Call — {peer_name}")
        self.resize(960, 620)
        self.setStyleSheet("background:#0d0d0d;")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinMaxButtonsHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._page = _VideoPage()
        self._view = QWebEngineView()
        self._view.setPage(self._page)
        self._view.setUrl(QUrl(call_url))
        layout.addWidget(self._view)

    def closeEvent(self, event):
        self._view.setUrl(QUrl("about:blank"))
        super().closeEvent(event)
