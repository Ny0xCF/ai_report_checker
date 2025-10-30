from dataclasses import dataclass
from typing import Optional, List
from src.bot.ai_client import ReportCheckResult

MAX_CHECKS = 5


@dataclass
class UserSession:
    user_id: int
    checks_remaining: int = MAX_CHECKS
    last_result: Optional[ReportCheckResult] = None
    active: bool = True
    processing: bool = False
    chat_history: List[dict] = None

    def __post_init__(self):
        if self.chat_history is None:
            self.chat_history = []

    def add_user_message(self, content: str):
        self.chat_history.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str):
        self.chat_history.append({"role": "assistant", "content": content})

    def can_check(self) -> bool:
        return self.active and self.checks_remaining > 0
