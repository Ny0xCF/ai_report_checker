import os
import io
import asyncio
from pathlib import Path
import logging
from typing import Optional, Dict, List
from dataclasses import dataclass

import discord
from discord.ext import commands

from src.bot.ai_client import AIClient, ReportCheckResult

# ----------------------- НАСТРОЙКА ЛОГГЕРА -----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("report-bot")

# ----------------------- КОНСТАНТЫ -----------------------
MAX_CHECKS = 5
START_CHANNEL_NAME = "проверка-отчетов"

# ----------------------- DTO -----------------------
@dataclass
class UserSession:
    user_id: int
    checks_remaining: int = MAX_CHECKS
    last_result: Optional[ReportCheckResult] = None
    active: bool = True
    processing: bool = False
    chat_history: List[dict] = None  # для хранения контекста общения с ИИ

    def __post_init__(self):
        if self.chat_history is None:
            self.chat_history = []


# ----------------------- UI VIEW -----------------------
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


# ----------------------- DISCORD BOT -----------------------
intents = discord.Intents.default()
intents.messages = True
intents.dm_messages = True
bot = commands.Bot(command_prefix="!", intents=intents)
sessions: Dict[int, UserSession] = {}

# ----------------------- AI CLIENT -----------------------
base_dir = Path(__file__).resolve().parent.parent
client = AIClient(
    env_path=Path(base_dir / ".env"),
    prompt_path=Path(base_dir / "prompts/arrest_report.txt"),
)

# ----------------------- ХЭНДЛЕРЫ -----------------------
@bot.event
async def on_ready():
    logger.info(f"Бот запущен как {bot.user}")
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=START_CHANNEL_NAME)
        if not channel:
            continue

        # Удаляем старое сообщение от бота (если было)
        async for msg in channel.history(limit=20):
            if msg.author == bot.user:
                await msg.delete()
                break

        # Создаем новое стартовое сообщение
        view = discord.ui.View()
        start_button = discord.ui.Button(label="🚔 Начать проверку", style=discord.ButtonStyle.primary)

        async def start_callback(interaction: discord.Interaction):
            user = interaction.user
            await interaction.response.send_message("📨 Я написал тебе в ЛС — проверь сообщения.", ephemeral=True)
            await user.send(
                "👋 Привет! Отправь сюда тело отчёта **текстом** или **.txt-файлом**.\n"
                "⚠️ Только тело, без оформления или кода."
            )
            sessions[user.id] = UserSession(user_id=user.id)
            logger.info(f"Создана новая сессия для {user.name}")

        start_button.callback = start_callback
        view.add_item(start_button)

        embed = discord.Embed(
            title="👮 Проверка полицейских отчётов",
            description="Нажмите кнопку ниже, чтобы начать проверку.",
            color=0x3498db
        )
        embed.set_image(url="https://i.imgur.com/1sRz2ZK.png")
        await channel.send(embed=embed, view=view)


# ----------------------- ОБРАБОТКА ЛС -----------------------
@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user or not isinstance(message.channel, discord.DMChannel):
        return

    session = sessions.get(message.author.id)
    if not session or not session.active:
        await message.channel.send("⚠️ У вас нет активной сессии. Начните проверку в канале бота.")
        return

    if session.processing:
        await message.channel.send("⏳ Отчёт уже отправлен. Подождите окончания текущей проверки.")
        return

    content = None
    if message.attachments:
        file = message.attachments[0]
        if not file.filename.endswith(".txt"):
            await message.channel.send("❌ Пришлите только .txt файл.")
            return
        content = (await file.read()).decode("utf-8")
    else:
        content = message.content.strip()

    if not content:
        await message.channel.send("⚠️ Не удалось прочитать отчёт. Попробуйте снова.")
        return

    session.processing = True
    processing_msg = await message.channel.send("🤖 Бот анализирует отчёт. Мне потребуется некоторое время...")

    try:
        # Добавляем контекст в историю
        session.chat_history.append({"role": "user", "content": content})

        # Отправляем ИИ контекст всей истории
        result = await client.query(content, history=session.chat_history)

        # Сохраняем результат и продолжаем историю
        session.last_result = result
        session.chat_history.append({"role": "assistant", "content": result.corrected_report})
        session.checks_remaining -= 1

        # Генерируем файл
        file_bytes = io.BytesIO(result.corrected_report.encode("utf-8"))
        discord_file = discord.File(file_bytes, filename="corrected_report.txt")

        # Отправляем результат
        view = ReportView(result, session)
        embed = view.make_embed()
        await message.channel.send(embed=embed, file=discord_file, view=view)

        # Отдельное уведомление
        await message.channel.send("✅ Проверка отчёта завершена! Ознакомьтесь с результатами выше.")

    except Exception as e:
        logger.exception("Ошибка при проверке отчёта")
        await processing_msg.edit(content=f"❌ Произошла ошибка при проверке: {e}")
    finally:
        session.processing = False

    if session.checks_remaining <= 0:
        session.active = False
        await message.channel.send("🚫 Лимит проверок исчерпан. Сессия завершена.")


# ----------------------- ЗАПУСК -----------------------
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN не найден в .env")
    bot.run(token)
