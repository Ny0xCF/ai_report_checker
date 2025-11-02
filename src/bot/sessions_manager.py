import asyncio
from typing import Dict

from src.bot.sessions import UserSession
from src.utils.config_loader import bot_config


class SessionManager:
    def __init__(self):
        self.sessions: Dict[int, UserSession] = {}

    async def create_session(self, user_id: int, dm_channel=None) -> UserSession | None:
        active_count = sum(1 for s in self.sessions.values() if s.active)
        if active_count >= bot_config.session.max_active:
            return None

        session = UserSession(user_id=user_id, dm_channel=dm_channel)
        loop = asyncio.get_event_loop()
        session.start_timeout(loop)
        self.sessions[user_id] = session
        return session

    def get(self, user_id: int) -> UserSession | None:
        return self.sessions.get(user_id)
