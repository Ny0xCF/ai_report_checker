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

ui_config = Dynaconf(settings_files=["src/configs/ui.yaml"])


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
            label=ui_config.message.initial.button.start.label,
            style=discord.ButtonStyle.green,
        )

        help_button = discord.ui.Button(
            label=ui_config.message.initial.button.help.label,
            style=discord.ButtonStyle.blurple,
        )

        # 📘 Обработчик нажатия на "Инструкцию"
        async def help_callback(interaction: discord.Interaction):
            await interaction.response.send_message(ui_config.message.help.description.text, ephemeral=True)

        # ⚙️ Обработчик нажатия "Начать проверку"
        async def start_callback(interaction: discord.Interaction):
            user = interaction.user

            # Проверяем, есть ли уже активная сессия
            existing_session = session_manager.get(user.id)
            if existing_session and existing_session.active:
                await interaction.response.send_message(ui_config.message.err_already_started, ephemeral=True)
                return

            # Создаём новую сессию
            session = await session_manager.create_session(user.id, dm_channel=user)
            if not session:
                await interaction.response.send_message(
                    ui_config.message.err_too_many_clients.description.text,
                    ephemeral=True
                )
                return

            # Пишем пользователю в ЛС
            try:
                await user.send(ui_config.message.start.description.text)
                await interaction.response.send_message(ui_config.message.start_notify.description.text, ephemeral=True)
                logger.info(f"Создана новая сессия для {user.name}")
            except discord.Forbidden:
                await interaction.response.send_message(ui_config.message.err_dm_closed.description.text,
                                                        ephemeral=True)
                session_manager.remove(user.id)
                return

        # Добавляем кнопки и колбэки
        start_button.callback = start_callback
        help_button.callback = help_callback
        view.add_item(start_button)
        view.add_item(help_button)

        # Основное embed-сообщение
        embed = discord.Embed(
            title=ui_config.message.initial.title.text,
            description=ui_config.message.initial.description.text,
            color=ui_config.message.initial.title.color
        )
        embed.set_image(url=ui_config.message.initial.image.url)

        await channel.send(embed=embed, view=view)


async def handle_dm(message: discord.Message):
    if message.author.bot:
        return

    session = session_manager.get(message.author.id)
    if not session or not session.active:
        await message.channel.send(ui_config.message.err_inactive_session.description.text)
        return

    # Сбрасываем таймер, если пользователь активен
    if not session.processing and session.checks_remaining > 0:
        session.dm_channel = message.channel
        session.reset_timeout()

    if session.processing:
        await message.channel.send(ui_config.message.err_pls_wait.description.text)
        return

    if message.attachments:
        file = message.attachments[0]
        if not file.filename.endswith(".txt"):
            await message.channel.send(ui_config.message.err_wrong_format.description.text)
            return
        content = (await file.read()).decode("utf-8")
    else:
        content = message.content.strip()

    if not content:
        await message.channel.send(ui_config.message.err_wrong_file_input.description.text)
        return

    session.processing = True
    processing_msg = await message.channel.send(ui_config.message.check_started.description.text)

    try:
        session.add_user_message(content)
        result = await client.query(content, history=session.chat_history)
        session.last_result = result
        session.add_assistant_message(result.corrected_report)
        session.checks_remaining -= 1

        file_bytes = io.BytesIO(result.corrected_report.encode("utf-8"))
        discord_file = discord.File(file_bytes, filename="report_example.txt")

        view = ReportView(result, session)
        embed = view.make_embed()
        await message.channel.send(embed=embed, file=discord_file, view=view)

    except Exception as e:
        logger.exception("Ошибка при проверке отчета")
        await processing_msg.edit(content=f"{ui_config.message.err_exception.description.text} {e}")
    finally:
        session.processing = False
        if session.active and session.checks_remaining > 0:
            session.reset_timeout()

    # Проверка лимита
    if session.checks_remaining <= 0:
        session.active = False
        if session.timeout_task and not session.timeout_task.done():
            session.timeout_task.cancel()

        await message.channel.send(ui_config.message.err_limit_reached.description.text)
