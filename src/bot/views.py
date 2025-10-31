import asyncio
import logging

import discord

from src.bot import sessions
from src.bot.ai_client import ReportCheckResult
from src.bot.sessions import UserSession

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
            title="📋 Результат проверки отчета",
            color=0x00b894,
            description=f"Осталось проверок: **{self.session.checks_remaining}**"
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
    @discord.ui.button(label="⏮ Назад", style=discord.ButtonStyle.secondary, custom_id="prev")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await self.update_message(interaction)

    @discord.ui.button(label="⏭ Вперед", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.total_pages - 1:
            self.page += 1
            await self.update_message(interaction)

    # ---------------- ЗАВЕРШЕНИЕ СЕССИИ ----------------
    @discord.ui.button(label="🚫 Завершить сессию", style=discord.ButtonStyle.red, custom_id="finish")
    async def finish_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._end_session(interaction, manual=True)

    # ---------------- ВНУТРЕННИЕ МЕТОДЫ ----------------
    async def _end_session(self, interaction: discord.Interaction, manual=False):
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
        try:
            await interaction.response.edit_message(view=new_view)
        except discord.errors.InteractionResponded:
            await interaction.edit_original_response(view=new_view)

        # Сообщение пользователю
        if manual:
            await interaction.followup.send("✅ Сессия завершена вручную", ephemeral=True)
            logger.info(f"Сессия пользователя {interaction.user} завершена вручную")
        else:
            try:
                await self.session.dm_channel.send(
                    "⏰ Сессия завершена автоматически из-за простоя. "
                    "Чтобы начать новую проверку, вернись в канал с интерфейсом бота и нажми на кнопку"
                )
            except Exception:
                logger.warning(f"Не удалось отправить сообщение о таймауте пользователю {self.session.user_id}")

    async def _session_timeout(self):
        try:
            await asyncio.sleep(sessions.SESSION_TIMEOUT)
            if self.session.active and not self.session.processing:
                # Только если сессия активна и сейчас нет проверки
                await self._end_session(interaction=None, manual=False)
        except asyncio.CancelledError:
            return  # Таймер сброшен
