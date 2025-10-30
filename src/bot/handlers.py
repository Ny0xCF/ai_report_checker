import io
import logging
import discord
from discord.ext import commands

from src.bot.views import ReportView
from src.bot.sessions import UserSession
from src.bot.ai_client import AIClient
from pathlib import Path

logger = logging.getLogger("report-bot")

START_CHANNEL_NAME = "проверка-отчетов"
sessions = {}

base_dir = Path(__file__).resolve().parent.parent
client = AIClient(
    env_path=base_dir / ".env",
    prompt_path=base_dir / "prompts/arrest_report.txt",
)


async def setup_start_message(bot: commands.Bot):
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=START_CHANNEL_NAME)
        if not channel:
            continue

        async for msg in channel.history(limit=20):
            if msg.author == bot.user:
                await msg.delete()
                break

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


async def handle_dm(message: discord.Message):
    if message.author.bot:
        return

    session = sessions.get(message.author.id)
    if not session or not session.can_check():
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
        session.add_user_message(content)
        result = await client.query(content, history=session.chat_history)
        session.last_result = result
        session.add_assistant_message(result.corrected_report)
        session.checks_remaining -= 1

        file_bytes = io.BytesIO(result.corrected_report.encode("utf-8"))
        discord_file = discord.File(file_bytes, filename="corrected_report.txt")

        view = ReportView(result, session)
        embed = view.make_embed()
        await message.channel.send(embed=embed, file=discord_file, view=view)
        await message.channel.send("✅ Проверка отчёта завершена!")

    except Exception as e:
        logger.exception("Ошибка при проверке отчёта")
        await processing_msg.edit(content=f"❌ Ошибка при проверке: {e}")
    finally:
        session.processing = False

    if session.checks_remaining <= 0:
        session.active = False
        await message.channel.send("🚫 Лимит проверок исчерпан. Сессия завершена.")
