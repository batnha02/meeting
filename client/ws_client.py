import json
import threading
import time
import websocket
from PyQt6.QtCore import QObject, pyqtSignal


class WSClient(QObject):
    connected      = pyqtSignal()
    disconnected   = pyqtSignal()
    message_in     = pyqtSignal(dict)   # any incoming message

    def __init__(self):
        super().__init__()
        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._url = ""

    def start(self, server_url: str, token: str):
        ws_base = server_url.replace("http://", "ws://").replace("https://", "wss://")
        self._url = f"{ws_base}/ws/{token}".rstrip("/")
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        while self._running:
            try:
                self._ws = websocket.WebSocketApp(
                    self._url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_close=self._on_close,
                    on_error=self._on_error,
                )
                self._ws.run_forever(ping_interval=25, ping_timeout=10)
            except Exception:
                pass
            if self._running:
                time.sleep(3)   # reconnect delay

    def _on_open(self, ws):
        self.connected.emit()

    def _on_message(self, ws, raw: str):
        try:
            data = json.loads(raw)
            self.message_in.emit(data)
        except Exception:
            pass

    def _on_close(self, ws, code, msg):
        self.disconnected.emit()

    def _on_error(self, ws, err):
        pass

    def send(self, payload: dict):
        if self._ws:
            try:
                self._ws.send(json.dumps(payload))
            except Exception:
                pass

    def stop(self):
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
