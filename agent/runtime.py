"""
프로세스 전체에서 단 하나의 SessionManager 인스턴스를 공유.
api.py 와 chat.py 둘 다 여기서 import 한다.
"""

from session_manager import SessionManager

manager = SessionManager()

# session_id 자체를 색 이름으로 사용 — 디렉토리도 동일 (red, blue, yellow, ...)
COLOR_PALETTE = ["red", "blue", "yellow", "pink", "purple", "orange", "cyan", "green"]


def next_color_id() -> str:
    """현재 활성 세션이 사용하지 않는 다음 색 이름을 반환. 다 쓰면 -2, -3 suffix."""
    used = {info.session_id for info in manager.list_sessions()}
    for c in COLOR_PALETTE:
        if c not in used:
            return c
    n = 2
    while True:
        for c in COLOR_PALETTE:
            cid = f"{c}-{n}"
            if cid not in used:
                return cid
        n += 1
