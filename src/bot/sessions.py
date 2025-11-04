import asyncio
from dataclasses import dataclass, field
from typing import Optional, List

import discord

from src.bot.ai_client import ReportCheckResult
from src.utils.config_loader import bot_config, messages_config


@dataclass
class UserSession:
    user_id: int
    checks_remaining: int = bot_config.bot.max_checks
    last_result: Optional[ReportCheckResult] = None
    active: bool = True
    processing: bool = False
    chat_history: List[dict] = field(default_factory=list)
    timeout_task: Optional[asyncio.Task] = None
    dm_channel: Optional[discord.abc.Messageable] = None  # discord.DMChannel для уведомления
    view: Optional[discord.ui.View] = None  # View для деактивации кнопок

    def add_user_message(self, content: str):
        self.chat_history.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str):
        self.chat_history.append({"role": "assistant", "content": content})

    def can_check(self) -> bool:
        return self.active and self.checks_remaining > 0

    def start_timeout(self, loop):
        """Запускает таймаут сессии"""
        if self.timeout_task and not self.timeout_task.done():
            self.timeout_task.cancel()
        self.timeout_task = loop.create_task(self._timeout_loop())

    def reset_timeout(self):
        """Сбрасывает таймаут, только если нет активной проверки и есть проверки"""
        if self.active and self.checks_remaining > 0 and not self.processing:
            loop = asyncio.get_event_loop()
            self.start_timeout(loop)

    async def _timeout_loop(self):
        try:
            await asyncio.sleep(bot_config.session.timeout)
            # Ждём завершения текущей проверки
            while self.processing:
                await asyncio.sleep(5)

            # Проверяем: если лимит проверок исчерпан, таймаут не нужен
            if self.checks_remaining <= 0 or not self.active:
                return

            # Завершаем сессию
            self.active = False

            # Деактивируем кнопки View
            if self.view:
                self.view.stop()
                for item in self.view.children:
                    if isinstance(item, discord.ui.Button):
                        item.disabled = True
                try:
                    # Обновляем сообщение с View, если возможно
                    await self.view.message.edit(view=self.view)
                except Exception:
                    pass

            if self.dm_channel:
                await self.dm_channel.send(
                    messages_config.message.session_closed_by_timeout.description.text
                )
        except asyncio.CancelledError:
            pass
