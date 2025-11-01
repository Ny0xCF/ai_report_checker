import io
import os
from pathlib import Path

import discord
from discord.ext import commands
from dynaconf import Dynaconf

from src.bot.ai_client import AIClient
from src.bot.sessions_manager import SessionManager
from src.bot.views import ReportView
from src.utils import logger

logger = logger.get_logger("handlers")

START_CHANNEL_NAME = os.getenv("START_CHANNEL_NAME", "проверка-отчетов")
session_manager = SessionManager()

base_dir = Path(__file__).resolve().parent.parent
client = AIClient(
    env_path=base_dir / ".env",
    prompt_path=base_dir / "configs/arrest_report.txt",
)

config = Dynaconf(settings_files=["src/configs/ui.yaml"])


async def setup_start_message(bot: commands.Bot):
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=START_CHANNEL_NAME)
        if not channel:
            continue

        # Удаляем старое сообщение с кнопками (если есть)
        async for msg in channel.history(limit=20):
            if msg.author == bot.user:
                await msg.delete()
                break

        # Создаем View с кнопками
        view = discord.ui.View(timeout=None)

        start_button = discord.ui.Button(
            label=config.message.initial.button.start.label,
            style=discord.ButtonStyle.green,
        )

        help_button = discord.ui.Button(
            label=config.message.initial.button.help.label,
            style=discord.ButtonStyle.blurple,
        )

        # 📘 Обработчик нажатия на "Инструкцию"
        async def help_callback(interaction: discord.Interaction):
            help_text = (
                "📘 **Инструкция по использованию бота:**\n\n"
                "1️⃣ Перейди в этот канал и нажми **«Начать проверку»**.\n"
                "2️⃣ Бот напишет тебе в личные сообщения. Если не пришло — проверь, "
                "что у тебя **разрешены ЛС от участников сервера**.\n"
                "3️⃣ Отправь **текст отчёта** или **.txt файл** в чат с ботом.\n"
                "4️⃣ Подожди, пока бот закончит анализ (он сообщит об этом).\n"
                "5️⃣ В ответ ты получишь исправленную версию отчёта и рекомендации.\n\n"
                "⚙️ **Советы:**\n"
                "- Можно отправлять только один отчёт за раз.\n"
                "- Проверка занимает от 10 до 60 секунд.\n"
                "- После нескольких проверок сессия завершится автоматически.\n\n"
                "💡 Если бот не отвечает или выдал ошибку — попробуй позже "
                "или напиши <@337950212016439327> для помощи."
            )
            await interaction.response.send_message(help_text, ephemeral=True)

        # ⚙️ Обработчик нажатия "Начать проверку"
        async def start_callback(interaction: discord.Interaction):
            user = interaction.user

            # Проверяем, есть ли уже активная сессия
            existing_session = session_manager.get(user.id)
            if existing_session and existing_session.active:
                await interaction.response.send_message(
                    "⚠️ У тебя уже есть активная проверка. Проверь свои личные сообщения со мной!",
                    ephemeral=True
                )
                return

            # Создаём новую сессию
            session = await session_manager.create_session(user.id, dm_channel=user)
            if not session:
                await interaction.response.send_message(
                    "⚠️ Сейчас слишком много активных проверок. Попробуй позже.",
                    ephemeral=True
                )
                return

            # Пишем пользователю в ЛС
            try:
                await user.send(
                    "👋 Привет! Отправь сюда только тело отчета в виде **текста** или **.txt-файла**. "
                    "Обрати внимание, что текст должен быть без какого-либо оформления или кода\n\n"
                    "⚠️ Я могу ошибаться, поэтому обязательно перепроверь рекомендации перед публикацией отчета!"
                )
                await interaction.response.send_message(
                    "✅ Я написал тебе в ЛС — проверь сообщения!",
                    ephemeral=True
                )
                logger.info(f"Создана новая сессия для {user.name}")
            except discord.Forbidden:
                await interaction.response.send_message(
                    "❌ Я не могу написать тебе в личные сообщения. Разреши ЛС и попробуй снова.",
                    ephemeral=True
                )
                session_manager.remove(user.id)
                return

        # Добавляем кнопки и колбэки
        start_button.callback = start_callback
        help_button.callback = help_callback
        view.add_item(start_button)
        view.add_item(help_button)

        # Основное embed-сообщение
        embed = discord.Embed(
            title=config.message.initial.title.text,
            description=config.message.initial.description.text,
            color=config.message.initial.title.color
        )
        embed.set_image(url=config.message.initial.image.url)

        await channel.send(embed=embed, view=view)


async def handle_dm(message: discord.Message):
    if message.author.bot:
        return

    session = session_manager.get(message.author.id)
    if not session or not session.active:
        await message.channel.send(
            "⚠️ У тебя нет активной сессии. Перейди в канал с интерфейсом бота и нажми на кнопку."
        )
        return

    # Сбрасываем таймер, если пользователь активен
    if not session.processing and session.checks_remaining > 0:
        session.dm_channel = message.channel
        session.reset_timeout()

    if session.processing:
        await message.channel.send("⏳ Отчет уже отправлен. Подожди окончания текущей проверки.")
        return

    if message.attachments:
        file = message.attachments[0]
        if not file.filename.endswith(".txt"):
            await message.channel.send("❌ Пришли файл в .txt формате.")
            return
        content = (await file.read()).decode("utf-8")
    else:
        content = message.content.strip()

    if not content:
        await message.channel.send("⚠️ Не удалось прочитать отчет. Попробуй еще раз.")
        return

    session.processing = True
    processing_msg = await message.channel.send(
        "🤖 Я анализирую твой отчет. Мне потребуется некоторое время..."
    )

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

    except Exception as e:
        logger.exception("Ошибка при проверке отчета")
        await processing_msg.edit(content=f"❌ Ошибка при проверке: {e}")
    finally:
        session.processing = False
        if session.active and session.checks_remaining > 0:
            session.reset_timeout()

    # Проверка лимита
    if session.checks_remaining <= 0:
        session.active = False
        if session.timeout_task and not session.timeout_task.done():
            session.timeout_task.cancel()

        await message.channel.send(
            "🚫 Лимит проверок исчерпан. Сессия завершена. "
            "Перейди в канал и нажми на кнопку, чтобы начать новую."
        )
