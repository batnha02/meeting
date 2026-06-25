import threading
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QScrollArea, QFrame, QListWidget,
    QListWidgetItem, QDialog, QSizePolicy, QTextEdit,
    QCheckBox, QDialogButtonBox, QStackedWidget, QSplitter,
    QMessageBox,
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QSize, QTimer, QThread, QObject,
)
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QFontMetrics,
    QPixmap, QPainterPath,
)

from api_client import APIClient
from ws_client import WSClient
from call_window import CallWindow


# ─── Avatar Widget ─────────────────────────────────────────────────────────────

class AvatarWidget(QLabel):
    def __init__(self, name: str, color: str = "#0084ff", size: int = 40, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._name = name
        self._color = QColor(color)
        self._size = size

    def set_name(self, name: str, color: str):
        self._name = name
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(0, 0, self._size, self._size)

        initials = "".join(w[0] for w in self._name.split() if w)[:2].upper() or "?"
        font = QFont("Segoe UI", max(self._size // 3, 8), QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QPen(QColor("white")))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, initials)
        painter.end()


# ─── Online Dot ────────────────────────────────────────────────────────────────

class OnlineDot(QWidget):
    def __init__(self, size=11, parent=None):
        super().__init__(parent)
        self.setFixedSize(size + 3, size + 3)
        self._size = size
        self._online = False

    def set_online(self, v: bool):
        self._online = v
        self.update()

    def paintEvent(self, _event):
        if not self._online:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#242526")))
        painter.drawEllipse(0, 0, self._size + 3, self._size + 3)
        painter.setBrush(QBrush(QColor("#31a24c")))
        painter.drawEllipse(2, 2, self._size - 1, self._size - 1)
        painter.end()


# ─── Contact Item ──────────────────────────────────────────────────────────────

class ContactItemWidget(QWidget):
    def __init__(self, data: dict, is_group: bool = False, parent=None):
        super().__init__(parent)
        self.data = data
        self.is_group = is_group
        self.setFixedHeight(68)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QWidget { background: transparent; border-radius: 10px; }")

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)

        # Avatar + online dot
        av_container = QWidget()
        av_container.setFixedSize(46, 46)
        self.avatar = AvatarWidget(data.get("name", data.get("display_name", "?")),
                                   data.get("avatar_color", "#0084ff"), 42, av_container)
        self.avatar.move(2, 2)

        self.dot = OnlineDot(11, av_container)
        self.dot.move(30, 30)
        self.dot.set_online(bool(data.get("is_online", False)))
        row.addWidget(av_container)

        # Text
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)

        display_name = data.get("name") or data.get("display_name") or "Unknown"
        self.name_label = QLabel(display_name)
        self.name_label.setStyleSheet("color: #e4e6ea; font-size: 14px; font-weight: 600;")
        self.name_label.setMaximumWidth(180)
        text_col.addWidget(self.name_label)

        last = data.get("last_message", "")
        self.last_label = QLabel(last[:40] + ("…" if len(last) > 40 else "") if last else "")
        self.last_label.setStyleSheet("color: #b0b3b8; font-size: 12px;")
        self.last_label.setMaximumWidth(180)
        text_col.addWidget(self.last_label)

        row.addLayout(text_col)
        row.addStretch()

    def update_online(self, online: bool):
        self.dot.set_online(online)
        self.data["is_online"] = online

    def update_last_message(self, text: str):
        self.data["last_message"] = text
        short = text[:40] + ("…" if len(text) > 40 else "")
        self.last_label.setText(short)


# ─── Message Bubble ────────────────────────────────────────────────────────────

class MessageBubble(QWidget):
    def __init__(self, content: str, sender_name: str, timestamp: str,
                 is_mine: bool, avatar_color: str = "#3a3b3c",
                 show_name: bool = False, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 3, 10, 3)
        outer.setSpacing(8)

        if is_mine:
            outer.addStretch()
            bubble_col = QVBoxLayout()
            bubble_col.setSpacing(2)
            bubble_col.setContentsMargins(0, 0, 0, 0)

            lbl = QLabel(content)
            lbl.setWordWrap(True)
            lbl.setMaximumWidth(480)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl.setStyleSheet("""
                background: #0084ff; color: white;
                border-radius: 18px; padding: 9px 14px;
                font-size: 14px; line-height: 1.4;
            """)
            bubble_col.addWidget(lbl, 0, Qt.AlignmentFlag.AlignRight)

            ts = QLabel(self._fmt_time(timestamp))
            ts.setStyleSheet("color: #65686e; font-size: 11px;")
            bubble_col.addWidget(ts, 0, Qt.AlignmentFlag.AlignRight)

            outer.addLayout(bubble_col)
        else:
            av = AvatarWidget(sender_name, avatar_color, 32)
            outer.addWidget(av, 0, Qt.AlignmentFlag.AlignBottom)

            bubble_col = QVBoxLayout()
            bubble_col.setSpacing(2)
            bubble_col.setContentsMargins(0, 0, 0, 0)

            if show_name:
                name_lbl = QLabel(sender_name)
                name_lbl.setStyleSheet("color: #b0b3b8; font-size: 11px; font-weight: 600; padding: 0 4px;")
                bubble_col.addWidget(name_lbl)

            lbl = QLabel(content)
            lbl.setWordWrap(True)
            lbl.setMaximumWidth(480)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl.setStyleSheet("""
                background: #3a3b3c; color: #e4e6ea;
                border-radius: 18px; padding: 9px 14px;
                font-size: 14px; line-height: 1.4;
            """)
            bubble_col.addWidget(lbl)

            ts = QLabel(self._fmt_time(timestamp))
            ts.setStyleSheet("color: #65686e; font-size: 11px; padding: 0 4px;")
            bubble_col.addWidget(ts)

            outer.addLayout(bubble_col)
            outer.addStretch()

    @staticmethod
    def _fmt_time(ts: str) -> str:
        if not ts:
            return ""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", ""))
            now = datetime.now()
            if dt.date() == now.date():
                return dt.strftime("%H:%M")
            return dt.strftime("%d/%m %H:%M")
        except Exception:
            return ""


# ─── Incoming Call Dialog ─────────────────────────────────────────────────────

class IncomingCallDialog(QDialog):
    accepted_call = pyqtSignal()
    rejected_call = pyqtSignal()

    def __init__(self, caller_name: str, caller_color: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cuộc gọi đến")
        self.setFixedSize(320, 260)
        self.setModal(False)
        self.setStyleSheet("QDialog { background: #242526; border-radius: 16px; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 28, 24, 24)
        layout.setSpacing(0)

        av = AvatarWidget(caller_name, caller_color, 72)
        layout.addWidget(av, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(14)

        name = QLabel(caller_name)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet("font-size: 18px; font-weight: 700; color: #e4e6ea;")
        layout.addWidget(name)

        info = QLabel("Đang gọi video cho bạn…")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("font-size: 13px; color: #b0b3b8; margin-top: 5px;")
        layout.addWidget(info)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)

        reject = QPushButton("📵  Từ chối")
        reject.setStyleSheet("""
            QPushButton { background: #ff3b30; color: white; border: none;
                border-radius: 22px; padding: 11px 24px; font-size: 14px; font-weight: 600; }
            QPushButton:hover { background: #e03429; }
        """)
        reject.clicked.connect(self._reject_call)
        btn_row.addWidget(reject)

        accept = QPushButton("📹  Nhận")
        accept.setStyleSheet("""
            QPushButton { background: #31a24c; color: white; border: none;
                border-radius: 22px; padding: 11px 24px; font-size: 14px; font-weight: 600; }
            QPushButton:hover { background: #279140; }
        """)
        accept.clicked.connect(self._accept_call)
        btn_row.addWidget(accept)

        layout.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._reject_call)
        self._timer.start(30_000)

    def _accept_call(self):
        self._timer.stop()
        self.accepted_call.emit()
        self.accept()

    def _reject_call(self):
        self._timer.stop()
        self.rejected_call.emit()
        self.reject()

    def closeEvent(self, event):
        self._reject_call()
        super().closeEvent(event)


# ─── Create Group Dialog ──────────────────────────────────────────────────────

class CreateGroupDialog(QDialog):
    def __init__(self, contacts: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tạo nhóm chat")
        self.setFixedSize(380, 480)
        self.setStyleSheet("""
            QDialog { background: #242526; }
            QLabel  { color: #e4e6ea; }
            QLineEdit {
                background: #3a3b3c; border: 1.5px solid transparent;
                border-radius: 8px; padding: 9px 12px; color: #e4e6ea; font-size: 13px;
            }
            QLineEdit:focus { border-color: #0084ff; }
            QCheckBox { color: #e4e6ea; font-size: 13px; spacing: 8px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px;
                background: #3a3b3c; border: 1.5px solid #65686e; }
            QCheckBox::indicator:checked { background: #0084ff; border-color: #0084ff; }
            QPushButton { border-radius: 8px; padding: 9px 20px; font-size: 14px; font-weight: 600; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Tạo nhóm chat mới")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        layout.addWidget(QLabel("Tên nhóm"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ví dụ: Nhóm dự án ABC…")
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("Thêm thành viên"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: #1c1e21; border-radius: 8px; border: none; }")
        scroll.setMinimumHeight(220)

        container = QWidget()
        container.setStyleSheet("background: #1c1e21;")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(10, 8, 10, 8)
        vbox.setSpacing(6)

        self.checks: list[tuple[int, QCheckBox]] = []
        for c in contacts:
            display = c.get("display_name", c.get("name", "?"))
            cb = QCheckBox(display)
            self.checks.append((c["id"], cb))
            vbox.addWidget(cb)

        vbox.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        self.err_label = QLabel("")
        self.err_label.setStyleSheet("color: #ff6b6b; font-size: 12px;")
        self.err_label.hide()
        layout.addWidget(self.err_label)

        btn_row = QHBoxLayout()
        cancel = QPushButton("Hủy")
        cancel.setStyleSheet("QPushButton { background: #3a3b3c; color: #e4e6ea; } QPushButton:hover { background: #4a4b4c; }")
        cancel.clicked.connect(self.reject)

        ok = QPushButton("Tạo nhóm")
        ok.setStyleSheet("QPushButton { background: #0084ff; color: white; } QPushButton:hover { background: #0073e0; }")
        ok.clicked.connect(self._create)

        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def _create(self):
        name = self.name_input.text().strip()
        if not name:
            self.err_label.setText("Vui lòng nhập tên nhóm")
            self.err_label.show()
            return
        selected = [uid for uid, cb in self.checks if cb.isChecked()]
        if len(selected) < 1:
            self.err_label.setText("Vui lòng chọn ít nhất 1 thành viên")
            self.err_label.show()
            return
        self.group_name = name
        self.selected_ids = selected
        self.accept()


# ─── Data Loader Thread ────────────────────────────────────────────────────────

class DataLoader(QObject):
    contacts_loaded = pyqtSignal(list, list)   # contacts, groups
    messages_loaded = pyqtSignal(list, object)  # messages, context

    def __init__(self, api: APIClient):
        super().__init__()
        self._api = api

    def load_contacts(self):
        def _run():
            try:
                contacts = self._api.get_contacts()
                groups   = self._api.get_groups()
                self.contacts_loaded.emit(contacts, groups)
            except Exception:
                self.contacts_loaded.emit([], [])
        threading.Thread(target=_run, daemon=True).start()

    def load_messages(self, other_id: int, context):
        def _run():
            try:
                msgs = self._api.get_messages(other_id)
                self.messages_loaded.emit(msgs, context)
            except Exception:
                self.messages_loaded.emit([], context)
        threading.Thread(target=_run, daemon=True).start()

    def load_group_messages(self, group_id: int, context):
        def _run():
            try:
                msgs = self._api.get_group_messages(group_id)
                self.messages_loaded.emit(msgs, context)
            except Exception:
                self.messages_loaded.emit([], context)
        threading.Thread(target=_run, daemon=True).start()


# ─── Messenger Window ──────────────────────────────────────────────────────────

class MessengerWindow(QMainWindow):
    def __init__(self, user_data: dict, server_url: str, api: APIClient):
        super().__init__()
        self.user = user_data
        self.server_url = server_url
        self.api = api

        self.current_chat_id: int | None = None
        self.current_is_group: bool = False
        self.contacts_map: dict[int, dict] = {}   # id -> contact data
        self.groups_map:   dict[int, dict] = {}   # id -> group data

        # Pending call (from_id, data)
        self._pending_call: dict | None = None
        self._active_call_window: CallWindow | None = None

        self.setWindowTitle(f"CompanyChat — {user_data['display_name']}")
        self.resize(1060, 700)
        self.setMinimumSize(800, 560)
        self.setStyleSheet("QMainWindow { background: #1c1e21; } QScrollBar:vertical { background: #1c1e21; width: 6px; border-radius: 3px; } QScrollBar::handle:vertical { background: #3a3b3c; border-radius: 3px; } QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; } QSplitter::handle { background: #3a3b3c; width: 1px; }")

        self._build_ui()

        # WebSocket
        self.ws = WSClient()
        self.ws.message_in.connect(self._on_ws_message)
        self.ws.start(server_url, api.token)

        # Data loader
        self.loader = DataLoader(api)
        self.loader.contacts_loaded.connect(self._on_contacts_loaded)
        self.loader.messages_loaded.connect(self._on_messages_loaded)
        self.loader.load_contacts()

        # Heartbeat
        self._hb = QTimer(self)
        self._hb.timeout.connect(lambda: self.ws.send({"type": "ping"}))
        self._hb.start(20_000)

    # ── Build UI ────────────────────────────────────────────────────────────

    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        self.setCentralWidget(splitter)

        # ── Left panel ──────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(300)
        left.setStyleSheet("background: #242526;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Header: avatar + name
        header = QWidget()
        header.setFixedHeight(64)
        header.setStyleSheet("background: #242526; border-bottom: 1px solid #3a3b3c;")
        h_row = QHBoxLayout(header)
        h_row.setContentsMargins(14, 0, 14, 0)

        self.my_avatar = AvatarWidget(
            self.user["display_name"], self.user.get("avatar_color", "#0084ff"), 36
        )
        h_row.addWidget(self.my_avatar)

        my_name = QLabel(self.user["display_name"])
        my_name.setStyleSheet("color: #e4e6ea; font-size: 14px; font-weight: 700;")
        h_row.addWidget(my_name)
        h_row.addStretch()

        new_group_btn = QPushButton("＋ Nhóm")
        new_group_btn.setStyleSheet("""
            QPushButton { background: #3a3b3c; color: #e4e6ea; border: none;
                border-radius: 8px; padding: 5px 10px; font-size: 12px; }
            QPushButton:hover { background: #4a4b4c; }
        """)
        new_group_btn.clicked.connect(self._create_group)
        h_row.addWidget(new_group_btn)
        left_layout.addWidget(header)

        # Search bar
        search_frame = QWidget()
        search_frame.setStyleSheet("background: #242526; padding: 8px 12px 4px 12px;")
        s_row = QHBoxLayout(search_frame)
        s_row.setContentsMargins(0, 0, 0, 0)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍  Tìm kiếm hoặc bắt đầu chat mới…")
        self.search_box.setStyleSheet("""
            QLineEdit { background: #3a3b3c; border: 1.5px solid transparent;
                border-radius: 20px; padding: 8px 16px; color: #e4e6ea; font-size: 13px; }
            QLineEdit:focus { border-color: #0084ff; }
        """)
        self.search_box.textChanged.connect(self._on_search)
        s_row.addWidget(self.search_box)
        left_layout.addWidget(search_frame)

        # Contact list
        self.contact_list = QListWidget()
        self.contact_list.setStyleSheet("""
            QListWidget { background: #242526; border: none; outline: none; }
            QListWidget::item { padding: 0; border: none; border-radius: 10px; }
            QListWidget::item:selected { background: #3a3b3c; }
            QListWidget::item:hover    { background: rgba(255,255,255,.05); }
        """)
        self.contact_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.contact_list.setSpacing(2)
        self.contact_list.currentItemChanged.connect(self._on_contact_selected)
        left_layout.addWidget(self.contact_list)

        splitter.addWidget(left)

        # ── Right panel ─────────────────────────────────────────
        right = QWidget()
        right.setStyleSheet("background: #1c1e21;")
        self.right_stack = QStackedWidget(right)
        right_outer = QVBoxLayout(right)
        right_outer.setContentsMargins(0, 0, 0, 0)
        right_outer.addWidget(self.right_stack)

        # Empty state
        empty = QWidget()
        empty.setStyleSheet("background: #1c1e21;")
        ev = QVBoxLayout(empty)
        ev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel("💬")
        icon.setStyleSheet("font-size: 64px;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ev.addWidget(icon)
        em = QLabel("Chọn một cuộc trò chuyện để bắt đầu")
        em.setStyleSheet("font-size: 15px; color: #65686e; margin-top: 12px;")
        em.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ev.addWidget(em)
        self.right_stack.addWidget(empty)   # index 0

        # Chat page
        chat_page = QWidget()
        chat_page.setStyleSheet("background: #1c1e21;")
        chat_layout = QVBoxLayout(chat_page)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        # Chat header
        self.chat_header = QFrame()
        self.chat_header.setFixedHeight(62)
        self.chat_header.setStyleSheet("background: #242526; border-bottom: 1px solid #3a3b3c;")
        ch_row = QHBoxLayout(self.chat_header)
        ch_row.setContentsMargins(16, 0, 16, 0)
        ch_row.setSpacing(10)

        self.header_avatar = AvatarWidget("?", "#0084ff", 40)
        ch_row.addWidget(self.header_avatar)

        name_col = QVBoxLayout()
        name_col.setSpacing(1)
        self.header_name = QLabel("—")
        self.header_name.setStyleSheet("font-size: 15px; font-weight: 700; color: #e4e6ea;")
        name_col.addWidget(self.header_name)
        self.header_status = QLabel("")
        self.header_status.setStyleSheet("font-size: 12px; color: #31a24c;")
        name_col.addWidget(self.header_status)
        ch_row.addLayout(name_col)
        ch_row.addStretch()

        self.video_call_btn = QPushButton("📹  Gọi video")
        self.video_call_btn.setStyleSheet("""
            QPushButton { background: rgba(0,132,255,.15); color: #0084ff; border: none;
                border-radius: 20px; padding: 7px 18px; font-size: 13px; font-weight: 600; }
            QPushButton:hover { background: rgba(0,132,255,.25); }
        """)
        self.video_call_btn.clicked.connect(self._start_video_call)
        ch_row.addWidget(self.video_call_btn)

        chat_layout.addWidget(self.chat_header)

        # Messages area
        self.msg_scroll = QScrollArea()
        self.msg_scroll.setWidgetResizable(True)
        self.msg_scroll.setStyleSheet("QScrollArea { border: none; background: #1c1e21; }")
        self.msg_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.msg_container = QWidget()
        self.msg_container.setStyleSheet("background: #1c1e21;")
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setContentsMargins(0, 12, 0, 8)
        self.msg_layout.setSpacing(2)
        self.msg_layout.addStretch()

        self.msg_scroll.setWidget(self.msg_container)
        chat_layout.addWidget(self.msg_scroll)

        # Input area
        input_frame = QFrame()
        input_frame.setStyleSheet("background: #242526; border-top: 1px solid #3a3b3c;")
        input_frame.setFixedHeight(72)
        i_row = QHBoxLayout(input_frame)
        i_row.setContentsMargins(14, 12, 14, 12)
        i_row.setSpacing(10)

        self.msg_input = QTextEdit()
        self.msg_input.setPlaceholderText("Aa")
        self.msg_input.setFixedHeight(46)
        self.msg_input.setStyleSheet("""
            QTextEdit { background: #3a3b3c; border: 1.5px solid transparent;
                border-radius: 22px; padding: 8px 16px;
                color: #e4e6ea; font-size: 14px; }
            QTextEdit:focus { border-color: #0084ff; }
        """)
        self.msg_input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        i_row.addWidget(self.msg_input)

        send_btn = QPushButton("➤")
        send_btn.setFixedSize(46, 46)
        send_btn.setStyleSheet("""
            QPushButton { background: #0084ff; color: white; border: none;
                border-radius: 23px; font-size: 18px; }
            QPushButton:hover  { background: #0073e0; }
            QPushButton:pressed { background: #0062bf; }
        """)
        send_btn.clicked.connect(self._send_message)
        i_row.addWidget(send_btn)

        chat_layout.addWidget(input_frame)

        self.right_stack.addWidget(chat_page)   # index 1

        splitter.addWidget(right)
        splitter.setSizes([300, 760])

        # Enter to send
        self.msg_input.installEventFilter(self)

    # ── Event Filter (Enter to send) ────────────────────────────────────────

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent
        if obj is self.msg_input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            mods = event.modifiers()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not (mods & Qt.KeyboardModifier.ShiftModifier):
                    self._send_message()
                    return True
        return super().eventFilter(obj, event)

    # ── Contact List ────────────────────────────────────────────────────────

    def _populate_contacts(self, contacts: list, groups: list):
        self.contact_list.clear()
        self.contacts_map.clear()
        self.groups_map.clear()

        for c in contacts:
            self.contacts_map[c["id"]] = c
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, {"type": "user", "id": c["id"]})
            item.setSizeHint(QSize(280, 68))
            widget = ContactItemWidget(c)
            self.contact_list.addItem(item)
            self.contact_list.setItemWidget(item, widget)

        for g in groups:
            g["name"] = g["name"]
            g_display = dict(g)
            g_display["display_name"] = g["name"]
            g_display["is_online"] = False
            self.groups_map[g["id"]] = g

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, {"type": "group", "id": g["id"]})
            item.setSizeHint(QSize(280, 68))
            widget = ContactItemWidget(g_display, is_group=True)
            self.contact_list.addItem(item)
            self.contact_list.setItemWidget(item, widget)

    def _on_contacts_loaded(self, contacts: list, groups: list):
        self._populate_contacts(contacts, groups)

    def _on_search(self, text: str):
        text = text.strip()
        if not text:
            self.loader.load_contacts()
            return

        def _run():
            try:
                results = self.api.search_users(text)
                self._populate_contacts(results, [])
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    def _on_contact_selected(self, current, _previous):
        if not current:
            return
        meta = current.data(Qt.ItemDataRole.UserRole)
        if not meta:
            return

        ctype = meta["type"]
        cid   = meta["id"]

        self.current_chat_id = cid
        self.current_is_group = (ctype == "group")

        # Clear messages
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.right_stack.setCurrentIndex(1)

        if ctype == "user":
            c = self.contacts_map.get(cid, {})
            name  = c.get("display_name", "?")
            color = c.get("avatar_color", "#0084ff")
            self.header_name.setText(name)
            self.header_status.setText("Đang hoạt động" if c.get("is_online") else "Ngoại tuyến")
            self.header_avatar.set_name(name, color)
            self.video_call_btn.show()
            self.loader.load_messages(cid, {"type": "user", "id": cid})
        else:
            g = self.groups_map.get(cid, {})
            name  = g.get("name", "Nhóm")
            color = g.get("avatar_color", "#0084ff")
            members = g.get("members", [])
            self.header_name.setText(name)
            self.header_status.setText(f"{len(members)} thành viên")
            self.header_avatar.set_name(name, color)
            self.video_call_btn.show()
            self.loader.load_group_messages(cid, {"type": "group", "id": cid})

    def _on_messages_loaded(self, messages: list, context):
        ctype = context["type"]
        cid   = context["id"]

        if self.current_chat_id != cid or self.current_is_group != (ctype == "group"):
            return

        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        prev_sender = None
        for msg in messages:
            is_mine = msg["sender_id"] == self.user["id"]
            show_name = ctype == "group" and not is_mine and msg["sender_id"] != prev_sender
            bubble = MessageBubble(
                msg["content"],
                msg.get("display_name", "?"),
                msg.get("timestamp", ""),
                is_mine,
                msg.get("avatar_color", "#3a3b3c"),
                show_name,
            )
            self.msg_layout.insertWidget(self.msg_layout.count() - 1, bubble)
            prev_sender = msg["sender_id"]

        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        sb = self.msg_scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── Send Message ────────────────────────────────────────────────────────

    def _send_message(self):
        if self.current_chat_id is None:
            return
        text = self.msg_input.toPlainText().strip()
        if not text:
            return

        self.msg_input.clear()

        payload: dict = {"type": "chat_message", "content": text}
        if self.current_is_group:
            payload["group_id"] = self.current_chat_id
        else:
            payload["receiver_id"] = self.current_chat_id

        self.ws.send(payload)

        bubble = MessageBubble(
            text, self.user["display_name"],
            datetime.now().isoformat(), True,
        )
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, bubble)
        QTimer.singleShot(30, self._scroll_to_bottom)

        widget = self._find_contact_widget(self.current_chat_id, self.current_is_group)
        if widget:
            widget.update_last_message(text)

    # ── WebSocket messages ──────────────────────────────────────────────────

    def _on_ws_message(self, msg: dict):
        mtype = msg.get("type")

        if mtype == "chat_message" and not msg.get("sent"):
            self._handle_incoming_message(msg)

        elif mtype == "user_status":
            uid    = msg["user_id"]
            online = msg["is_online"]
            if uid in self.contacts_map:
                self.contacts_map[uid]["is_online"] = online
            w = self._find_contact_widget(uid, False)
            if w:
                w.update_online(online)
            if self.current_chat_id == uid and not self.current_is_group:
                self.header_status.setText("Đang hoạt động" if online else "Ngoại tuyến")

        elif mtype == "call_request":
            self._on_incoming_call(msg)

        elif mtype == "call_accept":
            self._on_call_accepted(msg)

        elif mtype == "call_reject":
            self._on_call_rejected(msg)

        elif mtype == "call_end":
            if self._active_call_window:
                self._active_call_window.close()

    def _handle_incoming_message(self, msg: dict):
        sender_id = msg["sender_id"]
        group_id  = msg.get("group_id")

        if group_id:
            chat_id  = group_id
            is_group = True
        else:
            chat_id  = sender_id
            is_group = False

        # Add bubble if chat is open
        if self.current_chat_id == chat_id and self.current_is_group == is_group:
            is_mine = sender_id == self.user["id"]
            show_name = is_group and not is_mine
            bubble = MessageBubble(
                msg["content"],
                msg.get("display_name", "?"),
                msg.get("timestamp", datetime.now().isoformat()),
                is_mine,
                msg.get("avatar_color", "#3a3b3c"),
                show_name,
            )
            self.msg_layout.insertWidget(self.msg_layout.count() - 1, bubble)
            QTimer.singleShot(30, self._scroll_to_bottom)

        # Update last message in contact widget
        w = self._find_contact_widget(chat_id, is_group)
        if w:
            w.update_last_message(msg["content"])
        else:
            # New contact – reload
            self.loader.load_contacts()

    def _find_contact_widget(self, cid: int, is_group: bool) -> ContactItemWidget | None:
        for i in range(self.contact_list.count()):
            item = self.contact_list.item(i)
            meta = item.data(Qt.ItemDataRole.UserRole)
            if meta and meta["id"] == cid and (meta["type"] == "group") == is_group:
                return self.contact_list.itemWidget(item)
        return None

    # ── Video Call ──────────────────────────────────────────────────────────

    def _start_video_call(self):
        if self.current_chat_id is None:
            return

        if self.current_is_group:
            g = self.groups_map.get(self.current_chat_id, {})
            members = g.get("members", [])
            # For groups, notify all members
            self.ws.send({
                "type": "group_call_request",
                "group_id": self.current_chat_id,
                "caller_name": self.user["display_name"],
                "caller_color": self.user.get("avatar_color", "#0084ff"),
            })
            # Open call for each online member (simplified: open one call)
            for m in members:
                if m["id"] != self.user["id"] and manager_is_online(m["id"]):
                    self._open_call(m["id"], m["display_name"], m["avatar_color"], initiator=True)
            return

        c = self.contacts_map.get(self.current_chat_id, {})
        name  = c.get("display_name", "?")
        color = c.get("avatar_color", "#0084ff")

        self.ws.send({
            "type": "call_request",
            "target_id": self.current_chat_id,
            "caller_name": self.user["display_name"],
            "caller_color": self.user.get("avatar_color", "#0084ff"),
        })
        self._pending_call = {"target_id": self.current_chat_id, "name": name, "color": color}
        self._open_call(self.current_chat_id, name, color, initiator=True)

    def _open_call(self, target_id: int, name: str, color: str, initiator: bool):
        url = self.api.videocall_url(target_id, name, color, initiator)
        self._active_call_window = CallWindow(url, name, self)
        self._active_call_window.show()

    def _on_incoming_call(self, msg: dict):
        from_id     = msg["from_id"]
        caller_name = msg.get("caller_name", "Unknown")
        caller_color= msg.get("caller_color", "#0084ff")

        dlg = IncomingCallDialog(caller_name, caller_color, self)
        dlg.accepted_call.connect(lambda: self._accept_call(from_id, caller_name, caller_color))
        dlg.rejected_call.connect(lambda: self._reject_call(from_id))
        dlg.show()

    def _accept_call(self, from_id: int, name: str, color: str):
        self.ws.send({"type": "call_accept", "target_id": from_id})
        self._open_call(from_id, name, color, initiator=False)

    def _reject_call(self, from_id: int):
        self.ws.send({"type": "call_reject", "target_id": from_id})

    def _on_call_accepted(self, msg: dict):
        pass  # call window already open on initiator side

    def _on_call_rejected(self, msg: dict):
        from_id = msg.get("from_id")
        c = self.contacts_map.get(from_id, {})
        name = c.get("display_name", "Người dùng")
        if self._active_call_window:
            self._active_call_window.close()
            self._active_call_window = None
        QMessageBox.information(self, "Cuộc gọi bị từ chối", f"{name} đã từ chối cuộc gọi.")

    # ── Create Group ────────────────────────────────────────────────────────

    def _create_group(self):
        contacts = list(self.contacts_map.values())
        dlg = CreateGroupDialog(contacts, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        def _run():
            try:
                result = self.api.create_group(dlg.group_name, dlg.selected_ids)
                self.loader.load_contacts()
            except Exception as e:
                pass
        threading.Thread(target=_run, daemon=True).start()

    # ── Close ────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self.ws.stop()
        self.api.logout()
        super().closeEvent(event)


def manager_is_online(uid: int) -> bool:
    return False
