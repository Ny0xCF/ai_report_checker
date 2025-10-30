import discord

from src.bot.ai_client import ReportCheckResult
from src.bot.sessions import UserSession


class ReportView(discord.ui.View):
    def __init__(self, result: ReportCheckResult, session: UserSession):
        super().__init__(timeout=None)
        self.result = result
        self.session = session
        self.page = 0
        self.page_size = 5
        self.total_pages = max(1, (len(result.recommendations) - 1) // self.page_size + 1)
        self.update_buttons()

    def update_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id in {"prev", "next"}:
                child.disabled = self.total_pages <= 1

    def make_embed(self):
        embed = discord.Embed(
            title="📋 Результат проверки отчёта",
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
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="⏮ Назад", style=discord.ButtonStyle.secondary, custom_id="prev")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await self.update_message(interaction)

    @discord.ui.button(label="⏭ Вперёд", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.total_pages - 1:
            self.page += 1
            await self.update_message(interaction)

    @discord.ui.button(label="🚫 Завершить сессию", style=discord.ButtonStyle.red, custom_id="finish")
    async def finish_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.session.active = False
        await interaction.response.send_message("✅ Сессия завершена. Спасибо за работу!", ephemeral=True)
