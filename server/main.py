from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import hashlib
import json
import os
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Dict, Optional
import pathlib

SECRET_KEY = "company_chat_secret_key_2024_internal"
ALGORITHM = "HS256"
BASE_DIR = pathlib.Path(__file__).parent
DB_PATH = str(BASE_DIR / "chat.db")

app = FastAPI(title="CompanyChat Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AVATAR_COLORS = [
    "#0084ff", "#e4194d", "#f5a623", "#7b68ee",
    "#00b2c4", "#31a24c", "#ff6900", "#8b5cf6",
]


# ─── Database ─────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        avatar_color TEXT DEFAULT '#0084ff',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER,
        group_id INTEGER,
        content TEXT NOT NULL,
        msg_type TEXT DEFAULT 'text',
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        avatar_color TEXT DEFAULT '#0084ff',
        created_by INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS group_members (
        group_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        PRIMARY KEY (group_id, user_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS user_sessions (
        user_id INTEGER PRIMARY KEY,
        ip_address TEXT,
        last_seen TEXT,
        is_online INTEGER DEFAULT 0
    )""")

    admin_pw = hashlib.sha256("123456".encode()).hexdigest()
    c.execute("""INSERT OR IGNORE INTO users (username, display_name, password_hash, is_admin, avatar_color)
                 VALUES (?, ?, ?, 1, ?)""", ("admin", "Administrator", admin_pw, "#e4194d"))
    conn.commit()
    conn.close()


init_db()


# ─── Auth helpers ─────────────────────────────────────────────────────────────

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def create_token(user_id: int, username: str, is_admin: bool) -> str:
    payload = {
        "user_id": user_id,
        "username": username,
        "is_admin": is_admin,
        "exp": datetime.utcnow() + timedelta(days=7),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def auth_from_request(request: Request) -> Optional[dict]:
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    return verify_token(token) if token else None


# ─── WebSocket manager ────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.chat: Dict[int, WebSocket] = {}      # user_id -> ws (chat)
        self.signal: Dict[int, WebSocket] = {}    # user_id -> ws (webrtc signal)

    async def connect_chat(self, user_id: int, ws: WebSocket):
        await ws.accept()
        self.chat[user_id] = ws

    async def connect_signal(self, user_id: int, ws: WebSocket):
        await ws.accept()
        self.signal[user_id] = ws

    def disconnect_chat(self, user_id: int):
        self.chat.pop(user_id, None)

    def disconnect_signal(self, user_id: int):
        self.signal.pop(user_id, None)

    async def send_chat(self, user_id: int, msg: dict):
        ws = self.chat.get(user_id)
        if ws:
            try:
                await ws.send_text(json.dumps(msg))
            except Exception:
                self.disconnect_chat(user_id)

    async def send_signal(self, user_id: int, msg: dict):
        ws = self.signal.get(user_id)
        if ws:
            try:
                await ws.send_text(json.dumps(msg))
            except Exception:
                self.disconnect_signal(user_id)

    async def broadcast_chat(self, msg: dict, exclude: int = None):
        for uid, ws in list(self.chat.items()):
            if uid != exclude:
                try:
                    await ws.send_text(json.dumps(msg))
                except Exception:
                    self.disconnect_chat(uid)

    def is_online(self, user_id: int) -> bool:
        return user_id in self.chat

    def online_ids(self) -> list:
        return list(self.chat.keys())


manager = ConnectionManager()


# ─── REST: Auth ───────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
async def login(request: Request):
    data = await request.json()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    client_ip = request.client.host

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username=? AND password_hash=?",
        (username, hash_password(password)),
    ).fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không đúng")

    conn.execute(
        """INSERT OR REPLACE INTO user_sessions (user_id, ip_address, last_seen, is_online)
           VALUES (?, ?, ?, 1)""",
        (user["id"], client_ip, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    token = create_token(user["id"], user["username"], bool(user["is_admin"]))
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "is_admin": bool(user["is_admin"]),
            "avatar_color": user["avatar_color"],
        },
    }


@app.post("/api/auth/logout")
async def logout(request: Request):
    payload = auth_from_request(request)
    if payload:
        conn = get_db()
        conn.execute(
            "UPDATE user_sessions SET is_online=0 WHERE user_id=?",
            (payload["user_id"],),
        )
        conn.commit()
        conn.close()
    return {"success": True}


# ─── REST: Admin ──────────────────────────────────────────────────────────────

def require_admin(request: Request):
    payload = auth_from_request(request)
    if not payload or not payload.get("is_admin"):
        raise HTTPException(status_code=403, detail="Cần quyền admin")
    return payload


@app.get("/api/admin/users")
async def admin_list_users(request: Request):
    require_admin(request)
    conn = get_db()
    users = conn.execute(
        "SELECT id, username, display_name, is_admin, avatar_color, created_at FROM users ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(u) for u in users]


@app.post("/api/admin/users")
async def admin_create_user(request: Request):
    require_admin(request)
    data = await request.json()
    username = data.get("username", "").strip()
    display_name = data.get("display_name", "").strip()
    password = data.get("password", "")
    is_admin = int(data.get("is_admin", 0))

    if not username or not display_name or not password:
        raise HTTPException(status_code=400, detail="Thiếu thông tin bắt buộc")

    import random
    color = random.choice(AVATAR_COLORS)

    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO users (username, display_name, password_hash, is_admin, avatar_color) VALUES (?,?,?,?,?)",
            (username, display_name, hash_password(password), is_admin, color),
        )
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại")

    return {"success": True}


@app.put("/api/admin/users/{user_id}")
async def admin_update_user(user_id: int, request: Request):
    payload = require_admin(request)
    data = await request.json()
    display_name = data.get("display_name", "").strip()
    is_admin = int(data.get("is_admin", 0))

    conn = get_db()
    if data.get("password"):
        conn.execute(
            "UPDATE users SET display_name=?, password_hash=?, is_admin=? WHERE id=?",
            (display_name, hash_password(data["password"]), is_admin, user_id),
        )
    else:
        conn.execute(
            "UPDATE users SET display_name=?, is_admin=? WHERE id=?",
            (display_name, is_admin, user_id),
        )
    conn.commit()
    conn.close()
    return {"success": True}


@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: int, request: Request):
    payload = require_admin(request)
    if user_id == payload["user_id"]:
        raise HTTPException(status_code=400, detail="Không thể xóa chính mình")

    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.execute("DELETE FROM user_sessions WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"success": True}


# ─── REST: Users ──────────────────────────────────────────────────────────────

@app.get("/api/users/search")
async def search_users(q: str, request: Request):
    payload = auth_from_request(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Chưa xác thực")

    conn = get_db()
    rows = conn.execute(
        """SELECT u.id, u.username, u.display_name, u.avatar_color,
               COALESCE(s.is_online, 0) AS is_online
           FROM users u
           LEFT JOIN user_sessions s ON u.id=s.user_id
           WHERE (u.username LIKE ? OR u.display_name LIKE ?) AND u.id != ?
           ORDER BY u.display_name""",
        (f"%{q}%", f"%{q}%", payload["user_id"]),
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["is_online"] = bool(d["is_online"]) or manager.is_online(d["id"])
        result.append(d)
    return result


@app.get("/api/users/online")
async def get_online_users(request: Request):
    payload = auth_from_request(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Chưa xác thực")

    ids = manager.online_ids()
    conn = get_db()
    result = []
    for uid in ids:
        if uid == payload["user_id"]:
            continue
        u = conn.execute(
            "SELECT id, username, display_name, avatar_color FROM users WHERE id=?", (uid,)
        ).fetchone()
        if u:
            result.append(dict(u))
    conn.close()
    return result


@app.get("/api/users/me/contacts")
async def get_contacts(request: Request):
    """Return users I've recently chatted with + online users"""
    payload = auth_from_request(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Chưa xác thực")

    my_id = payload["user_id"]
    conn = get_db()

    # Users I've chatted with (direct messages)
    rows = conn.execute(
        """SELECT DISTINCT
               CASE WHEN sender_id=? THEN receiver_id ELSE sender_id END AS other_id
           FROM messages
           WHERE (sender_id=? OR receiver_id=?) AND receiver_id IS NOT NULL
           ORDER BY timestamp DESC""",
        (my_id, my_id, my_id),
    ).fetchall()

    contacted_ids = [r["other_id"] for r in rows if r["other_id"]]

    # Also add online users
    online_ids = manager.online_ids()
    all_ids = list(dict.fromkeys(contacted_ids + [i for i in online_ids if i != my_id]))

    result = []
    for uid in all_ids:
        u = conn.execute(
            "SELECT id, username, display_name, avatar_color FROM users WHERE id=?", (uid,)
        ).fetchone()
        if u:
            d = dict(u)
            d["is_online"] = manager.is_online(uid)
            # Last message
            last = conn.execute(
                """SELECT content, timestamp FROM messages
                   WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)
                   ORDER BY timestamp DESC LIMIT 1""",
                (my_id, uid, uid, my_id),
            ).fetchone()
            d["last_message"] = last["content"] if last else ""
            d["last_time"] = last["timestamp"] if last else ""
            result.append(d)
    conn.close()
    return result


# ─── REST: Messages ───────────────────────────────────────────────────────────

@app.get("/api/messages/{other_id}")
async def get_messages(other_id: int, request: Request):
    payload = auth_from_request(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Chưa xác thực")

    my_id = payload["user_id"]
    conn = get_db()
    rows = conn.execute(
        """SELECT m.id, m.sender_id, m.content, m.msg_type, m.timestamp,
               u.display_name, u.avatar_color
           FROM messages m
           JOIN users u ON m.sender_id=u.id
           WHERE (m.sender_id=? AND m.receiver_id=?)
              OR (m.sender_id=? AND m.receiver_id=?)
           ORDER BY m.timestamp ASC LIMIT 200""",
        (my_id, other_id, other_id, my_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/messages/group/{group_id}")
async def get_group_messages(group_id: int, request: Request):
    payload = auth_from_request(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Chưa xác thực")

    conn = get_db()
    # Verify membership
    member = conn.execute(
        "SELECT 1 FROM group_members WHERE group_id=? AND user_id=?",
        (group_id, payload["user_id"]),
    ).fetchone()
    if not member:
        conn.close()
        raise HTTPException(status_code=403, detail="Không có quyền truy cập nhóm")

    rows = conn.execute(
        """SELECT m.id, m.sender_id, m.content, m.msg_type, m.timestamp,
               u.display_name, u.avatar_color
           FROM messages m
           JOIN users u ON m.sender_id=u.id
           WHERE m.group_id=?
           ORDER BY m.timestamp ASC LIMIT 200""",
        (group_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── REST: Groups ─────────────────────────────────────────────────────────────

@app.get("/api/groups")
async def get_my_groups(request: Request):
    payload = auth_from_request(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Chưa xác thực")

    conn = get_db()
    groups = conn.execute(
        """SELECT g.id, g.name, g.avatar_color, g.created_at
           FROM groups g
           JOIN group_members gm ON g.id=gm.group_id
           WHERE gm.user_id=?
           ORDER BY g.created_at DESC""",
        (payload["user_id"],),
    ).fetchall()

    result = []
    for g in groups:
        d = dict(g)
        members = conn.execute(
            """SELECT u.id, u.display_name, u.avatar_color
               FROM group_members gm JOIN users u ON gm.user_id=u.id
               WHERE gm.group_id=?""",
            (g["id"],),
        ).fetchall()
        d["members"] = [dict(m) for m in members]

        last = conn.execute(
            "SELECT content, timestamp FROM messages WHERE group_id=? ORDER BY timestamp DESC LIMIT 1",
            (g["id"],),
        ).fetchone()
        d["last_message"] = last["content"] if last else ""
        d["last_time"] = last["timestamp"] if last else ""
        result.append(d)
    conn.close()
    return result


@app.post("/api/groups")
async def create_group(request: Request):
    payload = auth_from_request(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Chưa xác thực")

    data = await request.json()
    name = data.get("name", "").strip()
    member_ids = data.get("members", [])

    if not name:
        raise HTTPException(status_code=400, detail="Tên nhóm không được trống")

    import random
    color = random.choice(AVATAR_COLORS)

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO groups (name, avatar_color, created_by) VALUES (?,?,?)",
        (name, color, payload["user_id"]),
    )
    group_id = cur.lastrowid

    all_members = list(set(member_ids + [payload["user_id"]]))
    for uid in all_members:
        conn.execute(
            "INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?,?)",
            (group_id, uid),
        )
    conn.commit()
    conn.close()

    return {"group_id": group_id, "success": True}


@app.delete("/api/groups/{group_id}")
async def delete_group(group_id: int, request: Request):
    payload = auth_from_request(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Chưa xác thực")

    conn = get_db()
    g = conn.execute(
        "SELECT created_by FROM groups WHERE id=?", (group_id,)
    ).fetchone()
    if not g or g["created_by"] != payload["user_id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="Chỉ người tạo mới có thể xóa nhóm")

    conn.execute("DELETE FROM groups WHERE id=?", (group_id,))
    conn.execute("DELETE FROM group_members WHERE group_id=?", (group_id,))
    conn.execute("DELETE FROM messages WHERE group_id=?", (group_id,))
    conn.commit()
    conn.close()
    return {"success": True}


# ─── WebSocket: Chat ──────────────────────────────────────────────────────────

@app.websocket("/ws/{token}")
async def ws_chat(websocket: WebSocket, token: str):
    payload = verify_token(token)
    if not payload:
        await websocket.close(code=4001)
        return

    user_id = payload["user_id"]
    await manager.connect_chat(user_id, websocket)

    conn = get_db()
    conn.execute(
        "UPDATE user_sessions SET is_online=1, last_seen=? WHERE user_id=?",
        (datetime.now().isoformat(), user_id),
    )
    conn.commit()
    conn.close()

    await manager.broadcast_chat(
        {"type": "user_status", "user_id": user_id, "is_online": True},
        exclude=user_id,
    )

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == "chat_message":
                conn = get_db()
                cur = conn.execute(
                    "INSERT INTO messages (sender_id, receiver_id, group_id, content) VALUES (?,?,?,?)",
                    (user_id, msg.get("receiver_id"), msg.get("group_id"), msg["content"]),
                )
                msg_id = cur.lastrowid
                conn.commit()
                conn.close()

                forward = {
                    "type": "chat_message",
                    "id": msg_id,
                    "sender_id": user_id,
                    "receiver_id": msg.get("receiver_id"),
                    "group_id": msg.get("group_id"),
                    "content": msg["content"],
                    "timestamp": datetime.now().isoformat(),
                }

                if msg.get("receiver_id"):
                    await manager.send_chat(msg["receiver_id"], forward)

                elif msg.get("group_id"):
                    conn = get_db()
                    members = conn.execute(
                        "SELECT user_id FROM group_members WHERE group_id=?",
                        (msg["group_id"],),
                    ).fetchall()
                    conn.close()
                    for m in members:
                        if m["user_id"] != user_id:
                            await manager.send_chat(m["user_id"], forward)

                await manager.send_chat(user_id, {**forward, "sent": True})

            elif mtype in ("call_request", "call_accept", "call_reject", "call_end"):
                target_id = msg.get("target_id")
                if target_id:
                    await manager.send_chat(
                        target_id, {**msg, "from_id": user_id}
                    )

            elif mtype == "group_call_request":
                group_id = msg.get("group_id")
                if group_id:
                    conn = get_db()
                    members = conn.execute(
                        "SELECT user_id FROM group_members WHERE group_id=?", (group_id,)
                    ).fetchall()
                    conn.close()
                    for m in members:
                        if m["user_id"] != user_id:
                            await manager.send_chat(
                                m["user_id"],
                                {**msg, "from_id": user_id},
                            )

            elif mtype == "ping":
                await manager.send_chat(user_id, {"type": "pong"})

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_chat(user_id)
        conn = get_db()
        conn.execute(
            "UPDATE user_sessions SET is_online=0, last_seen=? WHERE user_id=?",
            (datetime.now().isoformat(), user_id),
        )
        conn.commit()
        conn.close()
        await manager.broadcast_chat(
            {"type": "user_status", "user_id": user_id, "is_online": False}
        )


# ─── WebSocket: WebRTC Signal ─────────────────────────────────────────────────

@app.websocket("/ws/signal/{token}")
async def ws_signal(websocket: WebSocket, token: str):
    payload = verify_token(token)
    if not payload:
        await websocket.close(code=4001)
        return

    user_id = payload["user_id"]
    await manager.connect_signal(user_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            target_id = msg.get("target_id")
            if target_id:
                await manager.send_signal(
                    target_id, {**msg, "from_id": user_id}
                )
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_signal(user_id)


# ─── Serve HTML pages ─────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_portal():
    html_path = BASE_DIR / "static" / "admin" / "index.html"
    return html_path.read_text(encoding="utf-8")


VIDEOCALL_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Video Call</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d0d0d;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;height:100vh;overflow:hidden;user-select:none}
#remote-video{position:fixed;inset:0;width:100%;height:100%;object-fit:cover;background:#1a1a2e}
#local-video{position:fixed;bottom:96px;right:16px;width:192px;height:128px;border-radius:14px;object-fit:cover;background:#000;border:2.5px solid rgba(255,255,255,0.3);box-shadow:0 4px 20px rgba(0,0,0,.5);transition:all .2s}
#local-video:hover{transform:scale(1.04)}
#peer-info{position:fixed;top:0;left:0;right:0;padding:28px 0 20px;text-align:center;background:linear-gradient(to bottom,rgba(0,0,0,.7),transparent);color:#fff}
#peer-avatar{width:64px;height:64px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:700;color:#fff;margin:0 auto 10px}
#peer-name{font-size:20px;font-weight:600;letter-spacing:.3px}
#call-status{font-size:14px;color:rgba(255,255,255,.7);margin-top:4px}
#controls{position:fixed;bottom:0;left:0;right:0;display:flex;align-items:center;justify-content:center;gap:18px;padding:24px 0 32px;background:linear-gradient(to top,rgba(0,0,0,.75),transparent)}
.ctrl-btn{width:58px;height:58px;border-radius:50%;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:24px;transition:transform .15s,background .2s;-webkit-tap-highlight-color:transparent}
.ctrl-btn:hover{transform:scale(1.1)}
.ctrl-btn:active{transform:scale(.95)}
.btn-toggle{background:rgba(255,255,255,.18);color:#fff;backdrop-filter:blur(8px)}
.btn-toggle.off{background:rgba(255,59,48,.85)}
.btn-end{background:#ff3b30;color:#fff;width:64px;height:64px;font-size:26px}
#no-video{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:16px;color:#fff;font-size:16px}
#no-video-avatar{width:96px;height:96px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:42px;font-weight:700}
#duration{position:fixed;top:14px;right:16px;background:rgba(0,0,0,.5);color:#fff;padding:4px 12px;border-radius:20px;font-size:13px;font-variant-numeric:tabular-nums}
</style>
</head>
<body>
<video id="remote-video" autoplay playsinline></video>
<video id="local-video"  autoplay playsinline muted></video>
<div id="no-video">
  <div id="no-video-avatar"></div>
  <span id="no-video-name"></span>
</div>
<div id="peer-info">
  <div id="peer-avatar"></div>
  <div id="peer-name"></div>
  <div id="call-status">Đang kết nối...</div>
</div>
<div id="duration" style="display:none">00:00</div>
<div id="controls">
  <button class="ctrl-btn btn-toggle" id="btn-mic"  title="Tắt mic">🎤</button>
  <button class="ctrl-btn btn-end"    id="btn-end"  title="Kết thúc">📵</button>
  <button class="ctrl-btn btn-toggle" id="btn-cam"  title="Tắt cam">📷</button>
</div>
<script>
const P = new URLSearchParams(location.search);
const token     = P.get('token');
const targetId  = +P.get('target_id');
const initiator = P.get('initiator')==='true';
const serverHost= P.get('server');
const peerName  = decodeURIComponent(P.get('name')||'User');
const peerColor = decodeURIComponent(P.get('color')||'#0084ff');

document.getElementById('peer-name').textContent = peerName;
document.getElementById('no-video-name').textContent = peerName;
const initials = peerName.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();
document.getElementById('peer-avatar').textContent = initials;
document.getElementById('peer-avatar').style.background = peerColor;
document.getElementById('no-video-avatar').textContent = initials;
document.getElementById('no-video-avatar').style.background = peerColor;

const rtcCfg = {iceServers:[{urls:'stun:stun.l.google.com:19302'}]};
let pc=null, localStream=null, micOn=true, camOn=true, startTime=null, timerInterval=null;

const remoteVideo = document.getElementById('remote-video');
const statusEl    = document.getElementById('call-status');
const noVideo     = document.getElementById('no-video');
const durationEl  = document.getElementById('duration');

const ws = new WebSocket(`ws://${serverHost}/ws/signal/${token}`);

function startTimer(){
  startTime=Date.now();
  durationEl.style.display='block';
  timerInterval=setInterval(()=>{
    const s=Math.floor((Date.now()-startTime)/1000);
    const m=Math.floor(s/60);
    durationEl.textContent=`${String(m).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;
  },1000);
}

ws.onopen = async()=>{
  statusEl.textContent='Đang khởi động camera...';
  await initMedia();
  if(initiator){ setTimeout(createOffer, 800); }
};

ws.onmessage = async(e)=>{
  const msg=JSON.parse(e.data);
  if(!pc) return;
  if(msg.type==='webrtc_offer' && !initiator){
    statusEl.textContent='Đang kết nối...';
    await pc.setRemoteDescription(new RTCSessionDescription(msg.sdp));
    const answer=await pc.createAnswer();
    await pc.setLocalDescription(answer);
    ws.send(JSON.stringify({type:'webrtc_answer',target_id:msg.from_id,sdp:pc.localDescription}));
  } else if(msg.type==='webrtc_answer'){
    await pc.setRemoteDescription(new RTCSessionDescription(msg.sdp));
  } else if(msg.type==='webrtc_ice'&&msg.candidate){
    try{ await pc.addIceCandidate(new RTCIceCandidate(msg.candidate)); }catch(err){}
  } else if(msg.type==='call_end'){
    endCall(false);
  }
};

async function initMedia(){
  try{
    localStream=await navigator.mediaDevices.getUserMedia({video:{width:640,height:480,facingMode:'user'},audio:true});
    document.getElementById('local-video').srcObject=localStream;
    pc=new RTCPeerConnection(rtcCfg);
    localStream.getTracks().forEach(t=>pc.addTrack(t,localStream));
    pc.ontrack=(ev)=>{
      if(ev.streams[0]){
        remoteVideo.srcObject=ev.streams[0];
        noVideo.style.display='none';
        startTimer();
      }
    };
    pc.onicecandidate=(ev)=>{
      if(ev.candidate) ws.send(JSON.stringify({type:'webrtc_ice',target_id:targetId,candidate:ev.candidate}));
    };
    pc.oniceconnectionstatechange=()=>{
      if(pc.iceConnectionState==='connected'||pc.iceConnectionState==='completed'){
        statusEl.textContent=peerName;
        document.getElementById('peer-info').style.display='none';
      } else if(pc.iceConnectionState==='failed'){
        statusEl.textContent='Kết nối thất bại';
        document.getElementById('peer-info').style.display='block';
      }
    };
    statusEl.textContent='Đang chờ kết nối...';
  } catch(err){
    statusEl.textContent='Lỗi camera/mic: '+err.message;
  }
}

async function createOffer(){
  if(!pc) return;
  statusEl.textContent='Đang thiết lập cuộc gọi...';
  const offer=await pc.createOffer({offerToReceiveAudio:true,offerToReceiveVideo:true});
  await pc.setLocalDescription(offer);
  ws.send(JSON.stringify({type:'webrtc_offer',target_id:targetId,sdp:pc.localDescription}));
}

function endCall(notify=true){
  if(notify) ws.send(JSON.stringify({type:'call_end',target_id:targetId}));
  clearInterval(timerInterval);
  if(localStream) localStream.getTracks().forEach(t=>t.stop());
  if(pc) pc.close();
  ws.close();
  window.close();
}

document.getElementById('btn-end').onclick=()=>endCall(true);

document.getElementById('btn-mic').onclick=function(){
  micOn=!micOn;
  if(localStream) localStream.getAudioTracks().forEach(t=>t.enabled=micOn);
  this.textContent=micOn?'🎤':'🔇';
  this.classList.toggle('off',!micOn);
};

document.getElementById('btn-cam').onclick=function(){
  camOn=!camOn;
  if(localStream) localStream.getVideoTracks().forEach(t=>t.enabled=camOn);
  this.textContent=camOn?'📷':'📵';
  this.classList.toggle('off',!camOn);
};
</script>
</body>
</html>"""


@app.get("/videocall", response_class=HTMLResponse)
async def videocall_page():
    return VIDEOCALL_HTML


@app.get("/")
async def root():
    return {"service": "CompanyChat Server", "version": "1.0", "admin_portal": "/admin"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
