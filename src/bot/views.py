import asyncio
import logging

import discord

from src.bot.ai_client import ReportCheckResult
from src.bot.sessions import UserSession
from src.utils.config_loader import messages_config, bot_config

logger = logging.getLogger("views")


class ReportView(discord.ui.View):
    def __init__(self, result: ReportCheckResult, session: UserSession):
        super().__init__(timeout=None)
        self.result = result
        self.session = session
        self.page = 0
        self.page_size = 5
        self.total_pages = max(1, (len(result.recommendations) - 1) // self.page_size + 1)
        self.timeout_task = asyncio.create_task(self._session_timeout())
        self.update_buttons()

    # ---------------- ОБНОВЛЕНИЕ СОСТОЯНИЯ ----------------
    def update_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id in {"prev", "next"}:
                child.disabled = self.total_pages <= 1

            # Кнопка завершения сессии блокируется, если сессия неактивна
            if isinstance(child, discord.ui.Button) and child.custom_id == "finish":
                child.disabled = not self.session.active

    def make_embed(self):
        embed = discord.Embed(
            title=messages_config.message.check_result.title.text,
            color=messages_config.message.check_result.title.color,
            description=f"{messages_config.message.check_result.description.text} **{self.session.checks_remaining}**"
        )
        start = self.page * self.page_size
        end = start + self.page_size
        subset = self.result.recommendations[start:end]
        for rec in subset:
            issues = "\n".join([f"• {i}" for i in rec.issues])
            embed.add_field(name=f"🔍 {rec.criterion}", value=issues or "Нет замечаний", inline=False)
        embed.set_footer(text=f"Страница {self.page + 1} из {self.total_pages}")
        return embed

    async def update_message(self, interaction: discord.Interaction):
        self.update_buttons()
        new_view = discord.ui.View()
        for item in self.children:
            new_view.add_item(item)
        try:
            await interaction.response.edit_message(embed=self.make_embed(), view=new_view)
        except discord.errors.InteractionResponded:
            await interaction.edit_original_response(embed=self.make_embed(), view=new_view)

    # ---------------- НАВИГАЦИЯ ----------------
    @discord.ui.button(label=messages_config.message.check_result.button.nav_back.label,
                       style=discord.ButtonStyle.secondary, custom_id="prev")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await self.update_message(interaction)

    @discord.ui.button(label=messages_config.message.check_result.button.nav_next.label,
                       style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.total_pages - 1:
            self.page += 1
            await self.update_message(interaction)

    # ---------------- ЗАВЕРШЕНИЕ СЕССИИ ----------------
    @discord.ui.button(label=messages_config.message.check_result.button.finish.label,
                       style=discord.ButtonStyle.primary,
                       custom_id="finish")
    async def finish_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._end_session(interaction, manual=True)

    # ---------------- ВНУТРЕННИЕ МЕТОДЫ ----------------
    async def _end_session(self, interaction: discord.Interaction | None, manual=False):
        if not self.session.active:
            return

        self.session.active = False

        # Останавливаем таймер
        if hasattr(self, "timeout_task") and self.timeout_task and not self.timeout_task.done():
            self.timeout_task.cancel()

        # Обновляем кнопки
        self.update_buttons()
        new_view = discord.ui.View()
        for item in self.children:
            new_view.add_item(item)

        # Обновляем сообщение, если interaction есть
        if interaction is not None:
            try:
                await interaction.response.edit_message(view=new_view)
            except discord.errors.InteractionResponded:
                await interaction.edit_original_response(view=new_view)

        # Отправляем уведомление пользователю
        try:
            if manual:
                if interaction is not None:
                    await interaction.followup.send(
                        messages_config.message.session_closed_ok.description.text,
                        ephemeral=True
                    )
                else:
                    await self.session.dm_channel.send(
                        messages_config.message.session_closed_ok.description.text
                    )
                logger.info(f"Сессия пользователя {self.session.user_id} завершена вручную")
            else:
                await self.session.dm_channel.send(
                    messages_config.message.session_closed_by_timeout.description.text
                )
                logger.info(f"Сессия пользователя {self.session.user_id} завершена по таймауту")
        except Exception:
            logger.warning(f"Не удалось отправить уведомление пользователю {self.session.user_id}")

    async def _session_timeout(self):
        try:
            await asyncio.sleep(bot_config.session.timeout)

            # Сессия активна и не в процессе обработки
            if self.session.active and not self.session.processing:
                await self._end_session(interaction=None, manual=False)
        except asyncio.CancelledError:
            return  # Таймер сброшен
