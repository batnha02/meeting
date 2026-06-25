import requests
from typing import Optional, List, Dict, Any


class APIClient:
    def __init__(self):
        self.base_url = ""
        self.token = ""
        self.session = requests.Session()
        self.session.timeout = 10

    def setup(self, server_url: str, token: str):
        self.base_url = server_url.rstrip("/")
        self.token = token
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _url(self, path: str) -> str:
        return self.base_url + path

    def login(self, server_url: str, username: str, password: str) -> Dict:
        url = server_url.rstrip("/") + "/api/auth/login"
        resp = requests.post(url, json={"username": username, "password": password}, timeout=8)
        resp.raise_for_status()
        return resp.json()

    def logout(self):
        try:
            self.session.post(self._url("/api/auth/logout"))
        except Exception:
            pass

    def get_contacts(self) -> List[Dict]:
        resp = self.session.get(self._url("/api/users/me/contacts"))
        resp.raise_for_status()
        return resp.json()

    def get_online_users(self) -> List[Dict]:
        resp = self.session.get(self._url("/api/users/online"))
        resp.raise_for_status()
        return resp.json()

    def search_users(self, query: str) -> List[Dict]:
        resp = self.session.get(self._url("/api/users/search"), params={"q": query})
        resp.raise_for_status()
        return resp.json()

    def get_messages(self, other_user_id: int) -> List[Dict]:
        resp = self.session.get(self._url(f"/api/messages/{other_user_id}"))
        resp.raise_for_status()
        return resp.json()

    def get_group_messages(self, group_id: int) -> List[Dict]:
        resp = self.session.get(self._url(f"/api/messages/group/{group_id}"))
        resp.raise_for_status()
        return resp.json()

    def get_groups(self) -> List[Dict]:
        resp = self.session.get(self._url("/api/groups"))
        resp.raise_for_status()
        return resp.json()

    def create_group(self, name: str, member_ids: List[int]) -> Dict:
        resp = self.session.post(
            self._url("/api/groups"),
            json={"name": name, "members": member_ids},
        )
        resp.raise_for_status()
        return resp.json()

    def delete_group(self, group_id: int):
        resp = self.session.delete(self._url(f"/api/groups/{group_id}"))
        resp.raise_for_status()

    def videocall_url(self, target_id: int, target_name: str, target_color: str, initiator: bool) -> str:
        from urllib.parse import quote
        host = self.base_url.replace("http://", "").replace("https://", "")
        return (
            f"{self.base_url}/videocall"
            f"?token={self.token}"
            f"&target_id={target_id}"
            f"&initiator={'true' if initiator else 'false'}"
            f"&server={host}"
            f"&name={quote(target_name)}"
            f"&color={quote(target_color)}"
        )
